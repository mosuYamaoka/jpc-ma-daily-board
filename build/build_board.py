#!/usr/bin/env python3
"""
M&A・出資デイリーボードのビルドスクリプト。

  python3 build_board.py --data deals_data.json --template template.html \
      --full  out/20260817_ma_daily_board.html \
      --public github/docs/index.html \
      --notify github/docs/notify.json \
      --new-dates 2026-08-17

役割:
  1. 30日ローリングの適用（--today からの日数で足切り）
  2. メタ情報（windowStart / windowEnd / updatedAt / updatedAtDisplay）の更新
  3. 完全版HTML（着眼点あり／アーティファクト用）の生成
  4. 公開版HTML（着眼点を除去／GitHub Pages用）の生成
  5. Teams通知用 notify.json の生成

公開版では insight フィールドをJSONごと削除するため、ページのソースにも残らない。
"""

import argparse
import copy
import json
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
SECTORS = ["PE", "商社・事業会社", "VC"]

PUBLIC_NOTE = (
    "本ページは公開プレスリリースを集約したものです。"
    "社内向けの着眼点コメントは本公開版には含まれません。"
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--template", required=True)
    ap.add_argument("--full", required=True, help="完全版HTMLの出力先")
    ap.add_argument("--public", help="公開版HTMLの出力先（省略可）")
    ap.add_argument("--notify", help="Teams通知用JSONの出力先（省略可）")
    ap.add_argument(
        "--new-dates",
        default="",
        help="今回追加した案件の日付をカンマ区切りで。新着件数の集計に使う",
    )
    ap.add_argument("--today", default="", help="基準日 YYYY-MM-DD（省略時は当日JST）")
    ap.add_argument("--window", type=int, default=30, help="保持日数（既定30）")
    args = ap.parse_args()

    now = datetime.now(JST)
    today = (
        datetime.strptime(args.today, "%Y-%m-%d").replace(tzinfo=JST)
        if args.today
        else now
    )
    cutoff = (today - timedelta(days=args.window - 1)).strftime("%Y-%m-%d")

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)

    # --- 30日ローリング ---
    before = len(data["deals"])
    data["deals"] = [d for d in data["deals"] if d["date"] >= cutoff]
    dropped = before - len(data["deals"])

    # --- 重複排除（buyer + target が同一なら後勝ちで1件に） ---
    seen, deduped = set(), []
    for d in sorted(data["deals"], key=lambda x: x["date"], reverse=True):
        key = (d["buyer"], d["target"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(d)
    data["deals"] = deduped

    # --- メタ情報 ---
    data["windowStart"] = cutoff
    data["windowEnd"] = today.strftime("%Y-%m-%d")
    data["updatedAt"] = now.isoformat(timespec="seconds")
    data["updatedAtDisplay"] = now.strftime("%Y/%m/%d %H:%M")
    data.pop("publicNote", None)

    with open(args.data, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    with open(args.template, encoding="utf-8") as f:
        tpl = f.read()

    def render(payload: dict, path: str) -> None:
        html = tpl.replace("__DATA__", json.dumps(payload, ensure_ascii=False))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)

    # --- 完全版（着眼点あり） ---
    render(data, args.full)

    # --- 公開版（着眼点を除去） ---
    if args.public:
        pub = copy.deepcopy(data)
        for d in pub["deals"]:
            d.pop("insight", None)
        pub["publicNote"] = PUBLIC_NOTE
        render(pub, args.public)

    # --- Teams通知用 ---
    new_dates = {s.strip() for s in args.new_dates.split(",") if s.strip()}
    new_deals = [d for d in data["deals"] if d["date"] in new_dates]
    by_sector = {s: sum(1 for d in new_deals if d["sector"] == s) for s in SECTORS}

    if args.notify:
        notify = {
            "dateLabel": today.strftime("%-m月%-d日"),
            "newCount": len(new_deals),
            "newBySector": {k: v for k, v in by_sector.items() if v},
            "totalCount": len(data["deals"]),
            "updatedAtDisplay": data["updatedAtDisplay"],
        }
        with open(args.notify, "w", encoding="utf-8") as f:
            json.dump(notify, f, ensure_ascii=False, indent=2)

    print(
        f"収録 {len(data['deals'])} 件 / 期間外削除 {dropped} 件 / "
        f"新着 {len(new_deals)} 件 {by_sector}"
    )


if __name__ == "__main__":
    main()
