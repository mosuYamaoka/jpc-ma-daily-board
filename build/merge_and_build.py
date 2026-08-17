#!/usr/bin/env python3
"""
差分JSONを既存の案件データにマージし、公開版HTMLとTeams通知用JSONを生成する。

  python3 build/merge_and_build.py --delta delta.json

処理:
  1. data/deals.json を読み込む
  2. 差分の generatedAt が実行日（JST）と一致する場合のみ新着として採用する
     （前日の差分を二重に取り込まないための安全弁）
  3. buyer + target で重複排除
  4. 実行日から30日より前の案件を削除（ローリング）
  5. data/deals.json を更新
  6. docs/index.html（着眼点を除いた公開版）を生成
  7. docs/notify.json（Teams通知用サマリ）を生成
"""

import argparse
import copy
import json
import os
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
SECTORS = ["PE", "商社・事業会社", "VC"]
WINDOW_DAYS = 30

PUBLIC_NOTE = (
    "本ページは公開プレスリリースを集約したものです。"
    "社内向けの着眼点コメントは本公開版には含まれません。"
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "deals.json")
TEMPLATE = os.path.join(ROOT, "build", "template.html")
PUBLIC_HTML = os.path.join(ROOT, "docs", "index.html")
NOTIFY = os.path.join(ROOT, "docs", "notify.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", required=True)
    args = ap.parse_args()

    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    cutoff = (now - timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d")

    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    with open(args.delta, encoding="utf-8") as f:
        delta = json.load(f)

    incoming = delta.get("deals", []) if delta.get("generatedAt") == today else []
    if delta.get("deals") and not incoming:
        print(
            f"::warning::差分の generatedAt={delta.get('generatedAt')} が本日({today})と"
            f"一致しないため、新着として採用しませんでした。"
        )

    existing_keys = {(d["buyer"], d["target"]) for d in data["deals"]}
    new_deals = [
        d for d in incoming if (d.get("buyer"), d.get("target")) not in existing_keys
    ]

    before = len(data["deals"])
    merged = data["deals"] + new_deals
    merged = [d for d in merged if d.get("date", "") >= cutoff]

    seen, deduped = set(), []
    for d in sorted(merged, key=lambda x: x.get("date", ""), reverse=True):
        key = (d.get("buyer"), d.get("target"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)

    dropped = before + len(new_deals) - len(deduped)

    data["deals"] = deduped
    data["windowStart"] = cutoff
    data["windowEnd"] = today
    data["updatedAt"] = now.isoformat(timespec="seconds")
    data["updatedAtDisplay"] = now.strftime("%Y/%m/%d %H:%M")

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()

    public = copy.deepcopy(data)
    for d in public["deals"]:
        d.pop("insight", None)
    public["publicNote"] = PUBLIC_NOTE

    os.makedirs(os.path.dirname(PUBLIC_HTML), exist_ok=True)
    with open(PUBLIC_HTML, "w", encoding="utf-8") as f:
        f.write(tpl.replace("__DATA__", json.dumps(public, ensure_ascii=False)))

    by_sector = {s: sum(1 for d in new_deals if d.get("sector") == s) for s in SECTORS}
    notify = {
        "dateLabel": f"{now.month}月{now.day}日",
        "newCount": len(new_deals),
        "newBySector": {k: v for k, v in by_sector.items() if v},
        "totalCount": len(data["deals"]),
        "updatedAtDisplay": data["updatedAtDisplay"],
    }
    with open(NOTIFY, "w", encoding="utf-8") as f:
        json.dump(notify, f, ensure_ascii=False, indent=2)

    print(
        f"新着 {len(new_deals)} 件 {by_sector} / 期間外削除・重複除去 {dropped} 件 / "
        f"収録 {len(data['deals'])} 件"
    )


if __name__ == "__main__":
    main()
