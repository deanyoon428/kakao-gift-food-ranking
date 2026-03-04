#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys

def load_items(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", []), data.get("fetched_at")
    except Exception:
        return [], None

def item_key(it: dict) -> str:
    return (it.get("product_url") or "").strip() or (it.get("title") or "").strip()

def safe_title(it: dict) -> str:
    return (it.get("title") or "").strip()

def summarize_changes(prev_items, cur_items, topn=10, max_lines=16):
    prev_map = {item_key(x): x for x in prev_items if item_key(x)}
    cur_map  = {item_key(x): x for x in cur_items if item_key(x)}

    prev_keys = set(prev_map.keys())
    cur_keys  = set(cur_map.keys())

    entered = [cur_map[k] for k in (cur_keys - prev_keys)]
    exited  = [prev_map[k] for k in (prev_keys - cur_keys)]

    moves = []
    for k in (prev_keys & cur_keys):
        p = prev_map[k]
        c = cur_map[k]
        pr = p.get("rank")
        cr = c.get("rank")
        if isinstance(pr, int) and isinstance(cr, int) and pr != cr:
            moves.append((pr, cr, c))
    moves.sort(key=lambda t: abs(t[0] - t[1]), reverse=True)

    prev_top = {item_key(x) for x in prev_items if isinstance(x.get("rank"), int) and x["rank"] <= topn and item_key(x)}
    cur_top  = {item_key(x) for x in cur_items  if isinstance(x.get("rank"), int) and x["rank"] <= topn and item_key(x)}
    top_in  = [cur_map[k] for k in (cur_top - prev_top) if k in cur_map]
    top_out = [prev_map[k] for k in (prev_top - cur_top) if k in prev_map]

    prev_1 = next((x for x in prev_items if x.get("rank") == 1), None)
    cur_1  = next((x for x in cur_items  if x.get("rank") == 1), None)
    first_changed = prev_1 and cur_1 and item_key(prev_1) != item_key(cur_1)

    changed = first_changed or bool(entered or exited or moves or (top_in or top_out))
    if not changed:
        return None

    lines = []
    if first_changed:
        lines.append("🥇 1위 변경")
        lines.append(f"- 이전: {safe_title(prev_1)}")
        lines.append(f"- 현재: {safe_title(cur_1)}")

    if top_in or top_out:
        lines.append(f"🔟 Top{topn} 변동")
        for it in sorted(top_in, key=lambda x: x.get("rank", 999))[:4]:
            lines.append(f"+ {it.get('rank')}위 {safe_title(it)}")
        for it in sorted(top_out, key=lambda x: x.get("rank", 999))[:4]:
            lines.append(f"- {it.get('rank')}위 {safe_title(it)}")

    if moves:
        lines.append("↕️ 순위 변동(큰 변화)")
        for pr, cr, it in moves[:6]:
            delta = pr - cr
            arrow = "⬆️" if delta > 0 else "⬇️"
            lines.append(f"{arrow} {safe_title(it)} ({pr}→{cr})")

    # 너무 길면 자르기
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["…(생략)"]

    return "\n".join(lines)

def main():
    if len(sys.argv) != 3:
        print("", end="")   # 워크플로우에서 빈 문자열 처리
        return 0

    prev_path, cur_path = sys.argv[1], sys.argv[2]
    prev_items, _ = load_items(prev_path)
    cur_items, _ = load_items(cur_path)

    msg = summarize_changes(prev_items, cur_items, topn=10)
    if not msg:
        print("변동 없음")
        return 0

    print(msg)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
