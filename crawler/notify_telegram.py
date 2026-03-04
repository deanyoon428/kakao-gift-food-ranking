#!/usr/bin/env python3
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

def load_items(path: str):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", []), data.get("fetched_at")
    except Exception:
        return [], None

def item_key(it: dict) -> str:
    # 가장 안정적인 키: product_url > title
    return (it.get("product_url") or "").strip() or (it.get("title") or "").strip()

def safe_title(it: dict) -> str:
    return (it.get("title") or "").strip()

def send_telegram(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }
    data = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read().decode("utf-8", errors="ignore")
    return body

def summarize_changes(prev_items, cur_items, topn=10, max_lines=18):
    prev_map = {item_key(x): x for x in prev_items if item_key(x)}
    cur_map  = {item_key(x): x for x in cur_items if item_key(x)}

    prev_keys = set(prev_map.keys())
    cur_keys  = set(cur_map.keys())

    entered = [cur_map[k] for k in (cur_keys - prev_keys)]
    exited  = [prev_map[k] for k in (prev_keys - cur_keys)]

    # rank changes (intersection)
    moves = []
    for k in (prev_keys & cur_keys):
        p = prev_map[k]
        c = cur_map[k]
        pr = p.get("rank")
        cr = c.get("rank")
        if isinstance(pr, int) and isinstance(cr, int) and pr != cr:
            moves.append((pr, cr, c))

    moves.sort(key=lambda t: abs(t[0] - t[1]), reverse=True)

    # topN sets
    prev_top = {item_key(x) for x in prev_items if isinstance(x.get("rank"), int) and x["rank"] <= topn and item_key(x)}
    cur_top  = {item_key(x) for x in cur_items  if isinstance(x.get("rank"), int) and x["rank"] <= topn and item_key(x)}
    top_in  = [cur_map[k] for k in (cur_top - prev_top) if k in cur_map]
    top_out = [prev_map[k] for k in (prev_top - cur_top) if k in prev_map]

    # 1st change
    prev_1 = next((x for x in prev_items if x.get("rank") == 1), None)
    cur_1  = next((x for x in cur_items  if x.get("rank") == 1), None)
    first_changed = prev_1 and cur_1 and item_key(prev_1) != item_key(cur_1)

    changed = first_changed or bool(entered or exited or moves or (top_in or top_out))
    if not changed:
        return None

    lines = []
    lines.append("📈 Kakao Gift 식품 랭킹 변동 리포트")

    if first_changed:
        lines.append("")
        lines.append("🥇 1위 변경")
        lines.append(f"- 이전: {safe_title(prev_1)}")
        lines.append(f"- 현재: {safe_title(cur_1)}")

    if top_in or top_out:
        lines.append("")
        lines.append(f"🔟 Top{topn} 변동")
        if top_in:
            # 현재 topN에 새로 들어온 애들
            top_in_sorted = sorted(top_in, key=lambda x: x.get("rank", 999))
            for it in top_in_sorted[:5]:
                lines.append(f"+ {it.get('rank')}위 {safe_title(it)}")
        if top_out:
            top_out_sorted = sorted(top_out, key=lambda x: x.get("rank", 999))
            for it in top_out_sorted[:5]:
                lines.append(f"- {it.get('rank')}위 {safe_title(it)}")

    if entered:
        lines.append("")
        lines.append("🆕 신규 진입(전체 리스트 기준)")
        for it in sorted(entered, key=lambda x: x.get("rank", 999))[:5]:
            lines.append(f"+ {it.get('rank')}위 {safe_title(it)}")

    if exited:
        lines.append("")
        lines.append("🚪 이탈(전체 리스트 기준)")
        for it in sorted(exited, key=lambda x: x.get("rank", 999))[:5]:
            lines.append(f"- {it.get('rank')}위 {safe_title(it)}")

    if moves:
        lines.append("")
        lines.append("↕️ 순위 변동(상위 변화 큰 순)")
        for pr, cr, it in moves[:6]:
            delta = pr - cr
            arrow = "⬆️" if delta > 0 else "⬇️"
            lines.append(f"{arrow} {safe_title(it)} ({pr}→{cr})")

    # 너무 길면 자르기
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["", "…(생략)"]

    return "\n".join(lines)

def main():
    if len(sys.argv) != 3:
        print("Usage: notify_telegram.py <prev.json> <cur.json>", file=sys.stderr)
        return 2

    prev_path, cur_path = sys.argv[1], sys.argv[2]
    prev_items, prev_ts = load_items(prev_path)
    cur_items, cur_ts = load_items(cur_path)

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not bot_token or not chat_id:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID env.", file=sys.stderr)
        return 3

    msg = summarize_changes(prev_items, cur_items, topn=10)
    if not msg:
        print("No meaningful changes detected. Skip notify.")
        return 0

    # 실행 링크(유용)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if repo and run_id:
        msg += f"\n\n🔗 Run: https://github.com/{repo}/actions/runs/{run_id}"

    # fetched time
    if cur_ts:
        msg += f"\n🕒 fetched_at: {cur_ts}"

    send_telegram(bot_token, chat_id, msg)
    print("Telegram notified.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
