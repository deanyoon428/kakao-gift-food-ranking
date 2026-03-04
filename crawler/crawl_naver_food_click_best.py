#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

URL = "https://snxbest.naver.com/product/best/click?categoryId=50000006&sortType=PRODUCT_CLICK&periodType=DAILY&ageType=MEN_30"
OUT = "docs/data/naver_food_click_best.json"
MAX_ITEMS = 100

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def norm_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())

def parse_items_from_text(lines):
    """
    페이지 텍스트 흐름이 대략 아래처럼 반복됨:
      * 1 위
      (이미지/찜하기 등)
      (스토어명) 상품명
      가격
      배송비...
    -> 'n 위' 라인을 기준으로 다음 상품명 라인을 탐지
    """
    items = []
    i = 0

    rank_pat = re.compile(r"^\*?\s*(\d+)\s*위\s*$")
    price_pat = re.compile(r"(\d[\d,]*)\s*원")

    while i < len(lines) and len(items) < MAX_ITEMS:
        m = rank_pat.match(lines[i])
        if not m:
            i += 1
            continue

        rank = int(m.group(1))
        title = None
        price = None
        store = None

        # 앞으로 몇 줄 훑어서 "스토어/상품명"과 "가격"을 잡음
        for j in range(i + 1, min(i + 25, len(lines))):
            s = lines[j]

            # 상품명 후보: 너무 짧지 않고, '배송비/별점/리뷰/할인율/원가/무료배송/네이버배송' 등 시스템 문구 제외
            if (
                len(s) >= 6
                and ("배송비" not in s)
                and ("별점" not in s)
                and ("리뷰" not in s)
                and ("할인율" not in s)
                and ("원가" not in s)
                and ("무료배송" not in s)
                and ("네이버배송" not in s)
                and ("찜하기" not in s)
            ):
                # 스토어명 형태가 같이 붙는 경우가 많아서, 앞에 대괄호/브랜드가 있든 그냥 타이틀이든 그대로 사용
                title = s
                # 스토어명은 title에서 첫 토큰이 "봉동당" 같은 경우라면 따로 추정(정확도 낮아도 OK)
                store = None
                break

        # 가격 후보
        for j in range(i + 1, min(i + 30, len(lines))):
            pm = price_pat.search(lines[j])
            if pm:
                price = pm.group(0).replace(" ", "")
                break

        if title:
            items.append(
                {
                    "rank": rank,
                    "title": norm_space(title),
                    "price": price,
                    "source_url": URL,
                    "store": store,
                }
            )

        i += 1

    # rank 정렬
    items.sort(key=lambda x: x.get("rank", 9999))
    return items

def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
    }

    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "lxml")
    text = soup.get_text("\n", strip=True)
    lines = [norm_space(x) for x in text.split("\n") if norm_space(x)]

    items = parse_items_from_text(lines)

    payload = {
        "source": URL,
        "fetched_at": utc_now_iso(),
        "items": items,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
