#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from collections import Counter

KAKAO = "docs/data/food_ranking.json"
NAVER = "docs/data/naver_food_click_best.json"

OUT_LATEST = "docs/data/keyword_latest.json"
OUT_TS = "docs/data/keyword_timeseries.ndjson"

# 식품 키워드 “시드”(원하면 계속 추가)
FOOD_SEED = {
    "딸기","샤인머스켓","한우","소고기","돼지고기","삼겹살","목살","치킨","닭가슴살",
    "케이크","초콜릿","쿠키","사탕","젤리","빵","디저트","과자","견과","호두",
    "참외","망고","사과","배","감귤","귤","과일",
    "피자","버거","도시락","샐러드","밀키트","만두","떡","모찌",
    "킹크랩","대게","회","해산물","수산",
    "프로틴","단백질","쉐이크","꿀","조청","생수","삼다수",
}

STOP = {
    "선물","세트","구성","증정","이벤트","기획","한정","특가","택1","택",
    "무료배송","배송","배송비","리뷰","별점","원","할인","원가","정기배송",
    "대용량","국내산","수입","냉동","냉장","산지직송","직송","당일","특품","프리미엄",
    "화이트데이","발렌타인","기념일",
}

WORD_RE = re.compile(r"[가-힣]{2,}|[A-Za-z]{3,}")

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_tokens(title: str):
    toks = []
    for m in WORD_RE.finditer(title or ""):
        t = m.group(0).strip()
        if not t or t in STOP:
            continue
        toks.append(t)
    return toks

def build_keyword_counts(kakao_items, naver_items):
    c = Counter()

    def add(items, weight):
        for it in items:
            title = (it.get("title") or "").strip()
            if not title:
                continue
            for t in extract_tokens(title):
                c[t] += weight

    # 카카오: 수요 근접 → 가중치 2
    add(kakao_items, 2)
    # 네이버 클릭베스트: 관심 → 가중치 1
    add(naver_items, 1)

    filtered = Counter()
    for k, v in c.items():
        if k in FOOD_SEED:
            filtered[k] = v
        else:
            # 시드가 아니면 노이즈 줄이기
            if v >= 4:
                filtered[k] = v
    return filtered

def load_last_timeseries():
    if not os.path.exists(OUT_TS):
        return None
    try:
        with open(OUT_TS, "r", encoding="utf-8") as f:
            lines = [x.strip() for x in f if x.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception:
        return None

def detect_spikes(prev_counts: dict, cur_counts: dict):
    spikes = []
    keys = set(prev_counts.keys()) | set(cur_counts.keys())
    for k in keys:
        prev = int(prev_counts.get(k, 0))
        cur = int(cur_counts.get(k, 0))

        # 너무 작은 값은 알림 대상에서 제외
        if cur < 5:
            continue

        delta = cur - prev
        ratio = (cur / prev) if prev > 0 else None

        # 급등 규칙(운영형)
        if delta >= 3 or (ratio is not None and ratio >= 2.0):
            spikes.append((k, cur, prev, delta, ratio))

    spikes.sort(key=lambda x: (x[3], x[1]), reverse=True)
    return spikes

def send_telegram(text: str):
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not bot_token or not chat_id:
        print("No TELEGRAM_* env. Skip notify.")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()

def main():
    os.makedirs(os.path.dirname(OUT_LATEST), exist_ok=True)

    kakao = load_json(KAKAO)
    naver = load_json(NAVER)

    kakao_items = kakao.get("items", []) or []
    naver_items = naver.get("items", []) or []

    cur_counts = build_keyword_counts(kakao_items, naver_items)
    cur_counts_dict = dict(cur_counts.most_common(60))

    prev = load_last_timeseries()
    prev_counts = (prev.get("keyword_counts") if prev else {}) or {}

    spikes = detect_spikes(prev_counts, cur_counts_dict)

    snapshot = {
        "fetched_at": utc_now_iso(),
        "sources": {
            "kakao": kakao.get("fetched_at"),
            "naver": naver.get("fetched_at"),
        },
        "keyword_counts": cur_counts_dict,
    }

    with open(OUT_LATEST, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    with open(OUT_TS, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    if spikes:
        top = spikes[:10]
        lines = ["🔥 식품 키워드 급등(카카오×2 + 네이버×1)"]
        for (k, cur, prevv, delta, ratio) in top:
            if ratio is None:
                lines.append(f"- {k}: {cur} (신규/급등, +{delta})")
            else:
                lines.append(f"- {k}: {cur} (이전 {prevv} → +{delta}, x{ratio:.1f})")

        repo = os.environ.get("GITHUB_REPOSITORY", "")
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        if repo and run_id:
            lines.append(f"\n🔗 Run: https://github.com/{repo}/actions/runs/{run_id}")

        send_telegram("\n".join(lines))
        print("Telegram spike alert sent.")
    else:
        print("No spikes detected.")

if __name__ == "__main__":
    main()
