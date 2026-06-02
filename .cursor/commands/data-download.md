---
name: /data-download
id: data-download
category: Workflow
description: 数据工程 · 多平台来源采集阶段
---

# data-download

## 命令目的
多平台分层源采集：权威源给实体主页补充，内容源给 post。

## 输入
- `--task {taskId}` `--batch {batchId}` `--entity-ids {a,b,c}`（可选 `--entity-type`，仅记录用）
- entities/{领域}/{类型}/{名称}/（来自 build，提供规范名/类型）
- Agent 预先填写的 `inputs/source_plan/{entityId}.json`（含 `sources[].url` 与可选 `body`）

## 来源平台

| 类型 | 权威源 | 内容源 |
|---|---|---|
| 实体定义 | wiki、百度百科、搜狗百科 | — |
| 文章 | — | 马蜂窝、小红书、穷游、携程、知乎、今日头条、微博、去哪儿 |
| 图片 | — | 小红书、马蜂窝、视觉中国 |
| 视频 | — | 抖音、B站、小红书 |

## Agent 检索范式（ReAct，单一真相源 = source_plan）

### 1. Agent 检索（web_search → 最小 source_plan）
对每个实体用 `web_search` 检索权威源（百科）+ 内容源（游记/攻略），把可用结果写进
`inputs/source_plan/{entityId}.json`：

```json
{
  "sources": [
    {"source_id": "baike_1", "platform": "baike", "url": "https://...", "body": "(正文摘录，去平台/作者/链接)"},
    {"source_id": "youji_1", "platform": "web",   "url": "https://...", "body": "..."}
  ],
  "imageUrls": [
    "https://upload.wikimedia.org/.../foo.jpg",
    {"url": "https://.../bar.jpg", "license": "CC BY-SA 4.0", "credit": "作者/来源"}
  ]
}
```

- 每实体 **≥2 条** planned source（gate `source_plan` 要求）；`body` 是裸 GET 失败时的离线兜底正文。
- 兼容 `sources` / `payload.sources` / `payload.existingSources` 三种形态。
- **图（必给）**：`imageUrls` 列实体级真实可用图直链（CC/PD/授权，优先 Wikimedia Commons 等明确版权源）；
  每项可为字符串或 `{url, license, credit}`；也可放在 `sources[].imageUrls`，下游去重合并。
  这是 produce 选图/`imageGate` 的唯一图源——**不给图则后续 review 必因「无可校验图片资源」阻断**。

### 2. CLI 抓取 + 兜底 + 打分（`qwq-data download`）
脚本对每个 url 裸 GET；失败 → 用 `body` 写离线兜底 `source.md`；`anonymize` 去平台/作者/URL；
`score_source_markdown` 打分并分级：

| 质量 | 阈值 | 处置 |
|---|---|---|
| A-story | score ≥ 7 | 保留（叙事丰富） |
| B-fact | score ≥ 4 | 保留（事实密集） |
| C-context | score ≥ 2 | 保留（上下文） |
| Reject | score < 2 | 剔除 |

产物：`sources/{entityId}/{sourceId}/{source.md, source.clean.md, source.quality.json}`，gate report 在 `results/`。

**图片采集**：按 `imageUrls` 跟随重定向下载真实图片二进制（按魔数判定，拒 HTML/错误页/过小图），
落 `sources/{entityId}/images/img_NN.{ext}` + `images/index.json`（含 license/credit/sha256），
并写 `image_fetch` gate report（下到 ≥1 张为 passed）。

### 3. ReAct 自省（证据充足性）
- `entity_source_bundle` gate 不过（retained < 1）或质量普遍 C/Reject → **再检索**：换更具体检索词
  （子景点/事实词/季节词）、补权威源；
- 仍不足 → 降级该实体或写入 `progress.openGaps`，并按 `/data-reflect` 记账（query/归因/决策）。

## validate
每实体 ≥1 retained 源、planned ≥2；不足走 ReAct 再检索或记 openGap。
