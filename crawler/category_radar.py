#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import re
from datetime import datetime, timezone
from collections import Counter, defaultdict
import urllib.parse, urllib.request

KAKAO = "docs/data/food_ranking.json"

OUT_SNAPSHOT = "docs/data/category_snapshot.json"
OUT_TS = "docs/data/category_timeseries.ndjson"

# ✅ 카테고리 사전(원하면 계속 튜닝)
CATEGORY_RULES = {
    "디저트/케이크": ["케이크","치즈케이크","롤케이크","마카롱","쿠키","초콜릿","브라우니","푸딩","디저트","빵","베이커리","도넛","젤리","사탕"],
    "한우/소고기": ["한우","소고기","등심","채끝","안심","불고기","갈비","꽃등심","LA갈비","육회","정육","스테이크"],
    "돼지고기": ["삼겹살","목살","돼지","오겹살","항정살","가브리살","보쌈","수육","돼지갈비"],
    "수산/해산물": ["대게","킹크랩","랍스터","전복","새우","회","광어","연어","해산물","수산","조개","가리비","새조개","장어"],
    "과일": ["딸기","샤인머스켓","머스캣","망고","사과","배","감귤","귤","한라봉","천혜향","레몬","바나나","포도","과일","참외","수박","복숭아"],
    "커피/음료": ["커피","라떼","원두","캡슐","차","티","녹차","홍차","음료","주스","탄산","콜라","사이다","에이드"],
    "건강/프로틴": ["단백질","프로틴","쉐이크","다이어트","저당","무설탕","비타민","홍삼","건강","영양","오메가","콜라겐"],
    "간편식/밀키트": ["밀키트","간편식","즉석","도시락","샐러드","파스타","리조또","볶음밥","국","탕","찌개"],
    "면/만두/떡": ["만두","떡","모찌","국수","면","라면","우동","짬뽕","파스타면","쌀국수"],
    "유제품/치즈": ["치즈","요거트","버터","우유","크림","생크림"],
    "견과/스낵": ["견과","호두","아몬드","피스타치오","과자","스낵","칩","바","시리얼"],
}

# ✅ 우선순위: "딸기치즈케이크" 같은 경우 과일보다 케이크로 가게
CATEGORY_PRIORITY = [
    "디저트/케이크",
    "유제품/치즈",
    "한우/소고기",
    "돼지고기",
    "수산/해산물",
    "간편식/밀키트",
    "면/만두/떡",
    "커피/음료",
    "건강/프로틴",
    "견과/스낵",
    "과일",
    "기타",
]

STOPWORDS = ["[단독]","[특가]","[한정]","[화이트데이]","증정","택1","쿠폰","선물","세트","구성"]

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def normalize_title(s: str) -> str:
    s = (s or "").strip()
    for w in STOPWORDS:
        s = s.replace(w, " ")
    s = re.sub(r"\s+"," ",s).strip()
    return s

def classify(title: str):
    """
    대표 카테고리 1개만.
    - 규칙 매칭 점수 계산
    - 점수가 같으면 CATEGORY_PRIORITY 순으로 결정(케이크가 과일보다 우선)
    """
    t = normalize_title(title).lower()
    scores = {}
    for cat, kws in CATEGORY_RULES.items():
        sc = 0
        for kw in kws:
            if kw.lower() in t:
                sc += 1
        if sc:
            scores[cat] = sc

    if not scores:
        return "기타", {}

    max_sc = max(scores.values())
    candidates = [c for c, sc in scores.items() if sc == max_sc]

    for cat in CATEGORY_PRIORITY:
        if cat in candidates:
            return cat, scores

    return candidates[0], scores

def load_last_snapshot():
    if not os.path.exists(OUT_SNAPSHOT):
        return None
    try:
        with open(OUT_SNAPSHOT,"r",encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def send_telegram(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat  = os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": text,
        "disable_web_page_preview": "true"
    }).encode("utf-8")
    urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST"), timeout=20).read()

def main():
    os.makedirs(os.path.dirname(OUT_SNAPSHOT), exist_ok=True)

    kakao = load_json(KAKAO)
    items = kakao.get("items") or []
    # ✅ Top100만
    items = [x for x in items if isinstance(x.get("rank"), int) and x["rank"] <= 100]
    items.sort(key=lambda x: x.get("rank", 999))

    counts = Counter()
    examples = defaultdict(list)  # cat -> [{rank,title,product_url}]
    for it in items:
        cat, _scores = classify(it.get("title",""))
        counts[cat] += 1
        if len(examples[cat]) < 3:
            examples[cat].append({
                "rank": it.get("rank"),
                "title": normalize_title(it.get("title","")),
                "product_url": it.get("product_url")
            })

    snapshot = {
        "source": kakao.get("source"),
        "fetched_at": kakao.get("fetched_at") or utc_now_iso(),
        "top_n": 100,
        "category_counts": dict(counts.most_common()),
        "category_examples": examples,
    }

    # 이전과 비교(직전 대비 Δ)
    prev = load_last_snapshot()
    prev_counts = (prev.get("category_counts") if prev else {}) or {}
    deltas = {}
    for cat in set(prev_counts.keys()) | set(snapshot["category_counts"].keys()):
        deltas[cat] = int(snapshot["category_counts"].get(cat, 0)) - int(prev_counts.get(cat, 0))
    snapshot["category_deltas_vs_prev"] = deltas

    # 저장
    with open(OUT_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    with open(OUT_TS, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")

    # 텔레그램: 변화가 있을 때만(원하면 항상 보내도록 바꿀 수 있음)
    changed = any(v != 0 for v in deltas.values()) if prev else True
    if changed:
        top = list(counts.most_common(7))
        lines = [f"📊 카카오 식품 Top100 카테고리 분포 ({snapshot['fetched_at']})"]
        for cat, c in top:
            d = deltas.get(cat, 0)
            sign = f"{d:+d}" if d else "0"
            lines.append(f"- {cat}: {c} (Δ {sign})")

        inc = sorted([(cat, d) for cat, d in deltas.items() if d >= 2], key=lambda x: x[1], reverse=True)
        if inc:
            lines.append("\n🔥 증가 카테고리(Δ>=+2)")
            for cat, d in inc[:5]:
                lines.append(f"+ {cat} (Δ +{d})")

        repo = os.environ.get("GITHUB_REPOSITORY","")
        run_id = os.environ.get("GITHUB_RUN_ID","")
        if repo and run_id:
            lines.append(f"\n🔗 Run: https://github.com/{repo}/actions/runs/{run_id}")

        send_telegram("\n".join(lines))

if __name__ == "__main__":
    main()
