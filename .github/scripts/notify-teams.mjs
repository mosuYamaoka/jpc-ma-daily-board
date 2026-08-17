/**
 * docs/notify.json を読み、新着があれば Teams の Workflows Webhook に
 * Adaptive Card を POST する。新着ゼロの日は何も投稿しない。
 *
 * 必要な環境変数:
 *   TEAMS_WEBHOOK_URL : Power Automate「Workflows」で発行した HTTP POST URL（GitHub Secrets）
 *   PAGE_URL          : GitHub Pages のURL（deployジョブの出力）
 */

import { readFileSync } from "node:fs";

const webhook = process.env.TEAMS_WEBHOOK_URL;
const pageUrl = (process.env.PAGE_URL || "").replace(/\/$/, "");

if (!webhook) {
  console.error("TEAMS_WEBHOOK_URL が未設定です。Secrets を確認してください。");
  process.exit(1);
}

let notify;
try {
  notify = JSON.parse(readFileSync("docs/notify.json", "utf8"));
} catch (e) {
  console.log("docs/notify.json が読めませんでした。投稿をスキップします。", e.message);
  process.exit(0);
}

const total = Number(notify.newCount ?? 0);
if (!total) {
  console.log("新着ゼロのため投稿をスキップしました。");
  process.exit(0);
}

const bySector = notify.newBySector || {};
const order = ["PE", "商社・事業会社", "VC"];
const label = { PE: "PEファンド", "商社・事業会社": "商社・事業会社", VC: "VCラウンド" };

const facts = order
  .filter((k) => Number(bySector[k]) > 0)
  .map((k) => ({ title: label[k], value: `${bySector[k]} 件` }));

const card = {
  type: "AdaptiveCard",
  $schema: "http://adaptivecards.io/schemas/adaptive-card.json",
  version: "1.4",
  body: [
    {
      type: "TextBlock",
      text: "M&A・出資デイリーボード",
      weight: "Bolder",
      size: "Medium",
      wrap: true,
    },
    {
      type: "TextBlock",
      text: `${notify.dateLabel ?? ""}　新着 **${total} 件**`,
      wrap: true,
      spacing: "None",
      isSubtle: true,
    },
    {
      type: "FactSet",
      facts: facts.length ? facts : [{ title: "内訳", value: "—" }],
    },
    {
      type: "TextBlock",
      text: `収録 ${notify.totalCount ?? "—"} 件（直近30日）`,
      wrap: true,
      isSubtle: true,
      size: "Small",
      spacing: "Small",
    },
  ],
  actions: [
    {
      type: "Action.OpenUrl",
      title: "ボードを開く",
      url: pageUrl || "https://github.com",
    },
  ],
};

const payload = {
  type: "message",
  attachments: [
    {
      contentType: "application/vnd.microsoft.card.adaptive",
      contentUrl: null,
      content: card,
    },
  ],
};

const res = await fetch(webhook, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(payload),
});

const body = await res.text();
if (!res.ok) {
  console.error(`Teams への POST が失敗しました: ${res.status} ${body}`);
  process.exit(1);
}
console.log(`Teams に投稿しました（新着 ${total} 件）。status=${res.status}`);
