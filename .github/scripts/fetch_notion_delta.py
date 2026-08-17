#!/usr/bin/env python3
"""
Notionの受け渡しページから当日分の差分JSONを取得し、標準出力ではなくファイルに書き出す。

環境変数:
  NOTION_TOKEN   : 内部コネクションのインストールアクセストークン（ntn_...）
  NOTION_PAGE_ID : 受け渡しページのID

出力:
  引数で指定したパス（既定 delta.json）に以下の形式で書き出す。
  取得できなかった場合も、空の差分として必ずファイルを作る（後段を止めないため）。

  {"generatedAt": "2026-08-18", "deals": [...]}
"""

import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.notion.com/v1"
# 新しいトークンで拒否された場合に備えて複数バージョンを順に試す
VERSIONS = ["2022-06-28", "2025-09-03"]


def request(path: str, version: str) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Notion-Version": version,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_blocks(page_id: str) -> list:
    last_err = None
    for version in VERSIONS:
        try:
            blocks, cursor = [], None
            while True:
                q = f"?page_size=100" + (f"&start_cursor={cursor}" if cursor else "")
                data = request(f"/blocks/{page_id}/children{q}", version)
                blocks.extend(data.get("results", []))
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
            print(f"Notion-Version {version} で取得成功（ブロック {len(blocks)} 件）")
            return blocks
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:400]
            last_err = f"HTTP {e.code}: {body}"
            print(f"Notion-Version {version} で失敗 → {last_err}")
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
            print(f"Notion-Version {version} で失敗 → {last_err}")
    raise RuntimeError(f"Notionからの取得に失敗しました。{last_err}")


def extract_last_code_block(blocks: list) -> str:
    texts = []
    for b in blocks:
        if b.get("type") != "code":
            continue
        parts = b["code"].get("rich_text", [])
        texts.append("".join(p.get("plain_text", "") for p in parts))
    if not texts:
        raise RuntimeError("受け渡しページにコードブロックが見つかりませんでした。")
    return texts[-1]


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "delta.json"
    fallback = {"generatedAt": "", "deals": [], "error": ""}

    try:
        page_id = os.environ["NOTION_PAGE_ID"].replace("-", "")
        blocks = fetch_blocks(page_id)
        raw = extract_last_code_block(blocks)
        delta = json.loads(raw)
        if not isinstance(delta.get("deals"), list):
            raise RuntimeError("deals 配列が見つかりません。")
        print(f"差分を取得しました：generatedAt={delta.get('generatedAt')} / {len(delta['deals'])} 件")
    except Exception as e:  # noqa: BLE001
        fallback["error"] = str(e)
        delta = fallback
        print(f"::warning::差分の取得に失敗したため空の差分として続行します: {e}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(delta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
