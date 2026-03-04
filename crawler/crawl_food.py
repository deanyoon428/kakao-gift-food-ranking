#!/usr/bin/env python3
"""
Kakao Gift 식품 랭킹 크롤러 (MVP, 운영형)
- 우선순위:
  1) 네트워크(JSON) 응답 자동 탐지/파싱
  2) DOM에서 링크/텍스트 기반 fallback 추출

출력:
- docs/data/food_ranking.json (최신 스냅샷)
- docs/data/food_history.ndjson (옵션: 히스토리 append)
- docs/data/debug/* (실패/디버깅 아티팩트)

주의:
- 페이지 구조 변경/차단 대응을 위해 로그를 남깁니다.
"""

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from playwright.sync_api import sync_playwright, TimeoutError as PwTimeoutError

URL = "https://gift.kakao.com/ranking/category/4"

DATA_DIR = os.path.join("docs", "data")
OUT_SNAPSHOT = os.path.join(DATA_DIR, "food_ranking.json")
OUT_HISTORY = os.path.join(DATA_DIR, "food_history.ndjson")
DEBUG_DIR = os.path.join(DATA_DIR, "debug")

MAX_ITEMS = 60
PAGE_TIMEOUT_MS = 60_000


@dataclass
class Item:
    rank: int
    title: str
    price: Optional[str] = None
    product_url: Optional[str] = None
    image_url: Optional[str] = None
    raw: Optional[dict] = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_mkdir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def dump_debug(path: str, content: bytes) -> None:
    safe_mkdir(os.path.dirname(path))
    with open(path, "wb") as f:
        f.write(content)


def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def looks_like_price(s: str) -> bool:
    s = (s or "").strip()
    return bool(re.search(r"(원|₩)\s*$", s)) or bool(re.search(r"\d[\d,]*\s*원", s))


def find_list_candidates(obj: Any) -> List[List[Any]]:
    """재귀적으로 리스트 후보들을 수집."""
    found: List[List[Any]] = []
    if isinstance(obj, list):
        found.append(obj)
        for x in obj:
            found.extend(find_list_candidates(x))
    elif isinstance(obj, dict):
        for v in obj.values():
            found.extend(find_list_candidates(v))
    return found


def score_product_list(lst: List[Any]) -> Tuple[int, List[Dict[str, Any]]]:
    """
    리스트가 '상품 리스트'일 가능성을 점수로 평가.
    - dict 원소 비율
    - title/name, price, image/url 같은 키 존재
    """
    if not lst:
        return 0, []
    dicts = [x for x in lst if isinstance(x, dict)]
    if len(dicts) < max(5, int(len(lst) * 0.4)):
        return 0, dicts

    keys = set()
    for d in dicts[:20]:
        keys |= set(d.keys())

    key_score = 0
    for k in ["name", "title", "productName", "displayName"]:
        if k in keys:
            key_score += 3
    for k in ["price", "salePrice", "discountPrice", "finalPrice", "originPrice"]:
        if k in keys:
            key_score += 2
    for k in ["image", "imageUrl", "thumbnail", "thumbnailUrl"]:
        if k in keys:
            key_score += 1
    for k in ["productId", "id", "itemId", "skuId"]:
        if k in keys:
            key_score += 2
    for k in ["link", "url", "productUrl"]:
        if k in keys:
            key_score += 1

    # length preference
    len_score = min(10, len(dicts) // 5)

    score = key_score + len_score
    return score, dicts


def parse_items_from_candidate(dicts: List[Dict[str, Any]]) -> List[Item]:
    items: List[Item] = []
    for idx, d in enumerate(dicts[:MAX_ITEMS], start=1):
        # title
        title = (
            d.get("title")
            or d.get("name")
            or d.get("productName")
            or d.get("displayName")
            or ""
        )
        title = normalize_space(str(title))

        # price candidates
        price = None
        for pk in ["price", "salePrice", "discountPrice", "finalPrice", "originPrice"]:
            if pk in d and d.get(pk) is not None:
                pv = d.get(pk)
                # 숫자면 원 붙이기
                if isinstance(pv, (int, float)):
                    price = f"{int(pv):,}원"
                else:
                    price = normalize_space(str(pv))
                break

        # url candidates
        product_url = None
        for uk in ["productUrl", "url", "link"]:
            if uk in d and d.get(uk):
                product_url = str(d.get(uk)).strip()
                break

        # image candidates
        image_url = None
        for ik in ["imageUrl", "thumbnailUrl", "thumbnail", "image"]:
            if ik in d and d.get(ik):
                image_url = str(d.get(ik)).strip()
                break

        if not title:
            # title이 없으면 스킵(노이즈)
            continue

        items.append(Item(rank=idx, title=title, price=price, product_url=product_url, image_url=image_url, raw=d))
    return items


def extract_from_dom(page) -> List[Item]:
    """
    DOM fallback:
    - 모든 a 태그 중 /product/ 포함 링크를 수집
    - 텍스트에서 상품명/가격을 heuristic하게 분리
    """
    anchors = page.locator("a")
    count = min(anchors.count(), 5000)

    seen = set()
    collected: List[Tuple[str, str]] = []

    for i in range(count):
        a = anchors.nth(i)
        href = a.get_attribute("href") or ""
        if "/product/" not in href:
            continue
        txt = normalize_space(a.inner_text() or "")
        if not txt:
            continue

        # 절대 URL로 정규화
        if href.startswith("/"):
            href = "https://gift.kakao.com" + href
        key = (href, txt)
        if key in seen:
            continue
        seen.add(key)
        collected.append((href, txt))
        if len(collected) >= MAX_ITEMS:
            break

    items: List[Item] = []
    for idx, (href, txt) in enumerate(collected, start=1):
        # 간단한 price heuristic: 텍스트 중 '원'이 있는 마지막 토큰을 price로
        price = None
        parts = txt.split(" ")
        for j in range(len(parts) - 1, -1, -1):
            if looks_like_price(parts[j]):
                price = parts[j]
                title = normalize_space(" ".join(parts[:j]))
                break
        else:
            title = txt

        title = normalize_space(title)
        if not title:
            continue

        items.append(Item(rank=idx, title=title, price=price, product_url=href))
    return items


def save_outputs(items: List[Item]) -> None:
    safe_mkdir(DATA_DIR)

    payload = {
        "source": URL,
        "fetched_at": utc_now_iso(),
        "items": [asdict(x) for x in items],
    }

    with open(OUT_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # history append (ndjson)
    with open(OUT_HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    safe_mkdir(DEBUG_DIR)

    captured_json: List[Tuple[str, Any]] = []

    def on_response(resp):
        try:
            ct = (resp.headers.get("content-type") or "").lower()
            if "application/json" not in ct:
                return
            url = resp.url
            # 랭킹 관련일 확률 높은 키워드
            if not re.search(r"(ranking|rank|category|gift|product|item)", url, re.IGNORECASE):
                return
            data = resp.json()
            captured_json.append((url, data))
        except Exception:
            return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.on("response", on_response)

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            # 동적 로딩 안정화용 대기
            page.wait_for_load_state("networkidle", timeout=PAGE_TIMEOUT_MS)
        except PwTimeoutError:
            pass
        except Exception as e:
            dump_debug(os.path.join(DEBUG_DIR, f"fatal_{utc_now_iso()}.txt"), str(e).encode("utf-8"))

        # 디버그 아티팩트 저장
        ts = utc_now_iso().replace(":", "").replace(".", "")
        try:
            page.screenshot(path=os.path.join(DEBUG_DIR, f"screenshot_{ts}.png"), full_page=True)
        except Exception:
            pass
        try:
            html = page.content().encode("utf-8")
            dump_debug(os.path.join(DEBUG_DIR, f"page_{ts}.html"), html)
        except Exception:
            pass

        # 네트워크 캡처 저장(상위 몇 개)
        try:
            dump_debug(
                os.path.join(DEBUG_DIR, f"network_{ts}.json"),
                json.dumps(
                    [{"url": u, "sample_keys": list(d.keys())[:40] if isinstance(d, dict) else str(type(d))}
                     for (u, d) in captured_json[:50]],
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8"),
            )
        except Exception:
            pass

        # 1) 네트워크 JSON에서 '상품 리스트' 자동 탐지
        best_items: List[Item] = []
        best_score = 0
        best_url = None

        for (u, data) in captured_json:
            candidates = find_list_candidates(data)
            for lst in candidates:
                score, dicts = score_product_list(lst)
                if score <= 0:
                    continue
                items = parse_items_from_candidate(dicts)
                if len(items) < 10:
                    continue
                # 점수 보정: 아이템 수가 많을수록 약간 가산
                score2 = score + min(10, len(items) // 10)
                if score2 > best_score:
                    best_score = score2
                    best_items = items
                    best_url = u

        # 2) fallback: DOM 추출
        if len(best_items) < 10:
            best_items = extract_from_dom(page)

        browser.close()

    # 최종 검증
    if len(best_items) < 10:
        # 실패: 디버그만 남기고 종료코드 1
        dump_debug(
            os.path.join(DEBUG_DIR, f"parse_failed_{ts}.txt"),
            f"Failed to parse enough items. captured_json={len(captured_json)} best_url={best_url}".encode("utf-8"),
        )
        return 1

    # best_url 기록 (디버그)
    try:
        dump_debug(
            os.path.join(DEBUG_DIR, f"best_source_{ts}.txt"),
            (best_url or "DOM_FALLBACK").encode("utf-8"),
        )
    except Exception:
        pass

    save_outputs(best_items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
