# Moltbot 飞书集成与 Cursor IDE 监控/任务下发方案

本文档说明：① 如何从 GitHub 更新 moltbot 代码；② 如何在飞书上集成 moltbot 并调用 QA 知识问答技能；③ 如何通过飞书**监控 Cursor IDE 中的开发状态**并**向 Cursor IDE 获取与下发开发任务**（被监控/被开发的对象可以是 quwoquan 工程，但**开发范围仅限 moltbot 与 Cursor IDE**，不修改 quwoquan 仓库）。

---

## 范围说明（必读）

- **开发范围**：仅 **moltbot** 与 **Cursor IDE** 的集成与飞书通道；不涉及 quwoquan 仓库内的代码或任务。
- **目标**：人在飞书查看「Cursor IDE 正在/已在 quwoquan 上做的开发」状态，并通过飞书向 Cursor IDE 下发新的开发任务；Cursor IDE 侧获取任务并上报状态。
- **quwoquan**：仅作为「被 Cursor 开发的工程」这一**对象**出现，不在此方案中改动 quwoquan 任何代码或配置。

---

## 1. 从 GitHub 更新 Moltbot 最新代码

### 1.1 当前状态

当前本机 `moltbot` 目录（`/Users/zhaoyuxi/Projects/moltbot`）**不是 Git 仓库**（无 `.git`），因此无法直接执行 `git pull`。

### 1.2 推荐做法

**方式 A：重新克隆（推荐，若可接受覆盖或迁移配置）**

```bash
# 备份现有配置与状态（若需保留）
cp -r ~/.clawdbot ~/.clawdbot.bak   # 状态与凭证
cp /Users/zhaoyuxi/Projects/moltbot/moltbot.json.example /tmp/  # 若曾改过

# 重命名或删除当前目录后克隆
cd /Users/zhaoyuxi/Projects
mv moltbot moltbot.old
git clone https://github.com/moltbot/moltbot.git
cd moltbot
pnpm install
```

**方式 B：在现有目录初始化 Git 并拉取（保留本地文件）**

```bash
cd /Users/zhaoyuxi/Projects/moltbot
git init
git remote add origin https://github.com/moltbot/moltbot.git
git fetch origin
# 若希望与 main 对齐且可接受覆盖本地修改：
git checkout -b main origin/main
# 或先备份后 reset：git reset --hard origin/main
```

之后日常更新：

```bash
cd /Users/zhaoyuxi/Projects/moltbot
git pull --rebase origin main
pnpm install
```

---

## 2. 飞书集成 Moltbot（含 QA 知识问答技能）

### 2.1 Moltbot 现有通道与技能机制

- **通道**：Moltbot 通过 **扩展（extensions）** 接入各 IM，如 `extensions/slack`、`extensions/telegram`、`extensions/discord` 等；**当前没有飞书（Feishu/Lark）官方扩展**。
- **消息流**：飞书消息 → 需自建「飞书通道插件」→ 转为 Moltbot 的 `MsgContext` → `dispatchInboundMessage` → Agent（含技能与工具）→ 回复经 `routeReply` → 通过同一通道插件发回飞书。
- **QA 技能**：Moltbot 的 QA 知识问答以 **Skill** 形式存在（如 `huawei-cloud-qa`、`crm-l2-qa`），位于 `skills/<name>/`，包含：
  - `SKILL.md`：技能描述与调用说明；
  - `scripts/run.sh`：执行入口，模型通过 **exec** 工具调用，例如：  
    `bash skills/huawei-cloud-qa/scripts/run.sh "用户问题"`  
  返回 JSON（如 `answer`、`ref_url`），由模型整理后回复用户。

只要飞书消息能进入 Moltbot 的 dispatch 流程，就会走同一套 Agent + 技能 + 工具；**无需单独“对接 QA 技能”**，只需在飞书通道里把用户问题当普通消息送入即可。

### 2.2 飞书开放平台要点（接收与发送消息）

- **接收消息**：订阅「接收消息 v2.0」事件（`im.message.receive_v1`）。可选：
  - **长连接（推荐）**：用飞书 SDK 建 WebSocket，无需公网 IP，适合本地/内网。
  - **Webhook**：提供公网 URL，飞书 POST 到该 URL。
- **发送消息**：调用 OpenAPI，例如：
  - `im/v1/messages`，`receive_id_type` + `receive_id` + `content`（JSON 字符串，如 `{"text":"hello"}`）+ `msg_type: "text"`。

参考：
- 开发文档：<https://open.feishu.cn/document>
- 机器人概览：<https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/bot-v3/bot-overview>
- 接收消息：<https://open.feishu.cn/document>（消息与群组 → 接收消息 v2.0）

### 2.3 实现思路：新增飞书通道扩展

在 moltbot 仓库中新增 **`extensions/feishu`**，参考 `extensions/slack` 结构：

1. **包与入口**
   - `extensions/feishu/package.json`：`moltbot.extensions: ["./index.ts"]`，依赖仅放 extension 所需（如飞书 SDK）。
   - `extensions/feishu/index.ts`：实现 `MoltbotPluginApi`，`registerChannel({ plugin: feishuPlugin })`。

2. **ChannelPlugin 实现（参考 Slack）**
   - **入站**：飞书事件订阅（长连接或 Webhook）→ 解析 `im.message.receive_v1` → 构造 `MsgContext`（`Body`、`From`、`To`、`SessionKey`、`MessageSid`、`ReplyToId` 等）→ 调用核心 **dispatch 入口**（与 Slack/Telegram 相同），即把消息交给 `dispatchInboundMessage`，由现有 Agent + 技能 + 工具 处理。
   - **出站**：实现 `ChannelPlugin.outbound`（`sendText`、`sendMedia`、可选 `chunker`、`resolveTarget`），在实现里调飞书 `im/v1/messages` 等接口，把 Agent 的回复发回飞书会话/群。
   - **SessionKey**：与现有规则一致，例如单聊 `agent:main:feishu:user:<open_id>`，群聊 `agent:main:feishu:group:<chat_id>`，便于路由与多会话隔离。
   - **配置**：在 `moltbot.json` 中增加 `channels.feishu`（app_id、app_secret、verification_token 等），与飞书应用配置一致。

3. **核心注册与路由**
   - Moltbot 的 `routeReply` 使用 `normalizeChannelId` → `normalizeAnyChannelId`，会从**插件注册表**解析 channel；只要插件 id 为 `feishu` 并实现 `outbound`，回复就会通过 `loadChannelOutboundAdapter("feishu")` 走到你的飞书发送逻辑。
   - 若希望 CLI/配置里出现“飞书”选项，需在 **`src/channels/registry.ts`** 的 `CHAT_CHANNEL_ORDER` 与 `CHAT_CHANNEL_META` 中增加 `feishu`（与现有 slack/telegram 同列），否则仅通过插件注册也可路由（插件 channel 会进入 `listPluginChannelIds()`，已算可投递通道）。

4. **QA 技能在飞书中的表现**
   - 用户在飞书里提问（如「华为云大模型怎么收费？」）→ 飞书插件把该句作为 `Body` 送入 dispatch → Agent 使用系统提示词 + 当前 workspace 的 skills（如 `huawei-cloud-qa`）→ 模型决定调用 `exec` 执行 `run.sh "..."` → 得到 JSON 后整理回复 → 出站通过同一飞书插件发回飞书。
   - 无需为飞书单独写“调用 QA 技能”的接口；**只要 workspace 里启用了对应 skill（如 `skills.entries` 或 allowlist 中包含 huawei-cloud-qa），飞书进来的会话就会自动具备该能力**。

### 2.4 小结：飞书 + QA 技能

- **集成飞书**：新增 `extensions/feishu`，实现收（事件→MsgContext→dispatch）、发（outbound→飞书 API）、配置与 SessionKey。
- **调用 QA 知识问答**：不区分渠道；飞书消息进入同一 Agent 流程，由现有 skills（如 huawei-cloud-qa）通过 exec 被模型调用即可。

### 2.5 飞书扩展 Webhook 与配置（extensions/feishu）

在 moltbot 仓库中已提供 **`extensions/feishu`** 扩展，使用方式如下。

- **Webhook 路径**：Gateway 启动后，飞书事件订阅请求需指向 **`/feishu`**（完整 URL 示例：`https://你的公网域名/feishu`）。在飞书开放平台「事件订阅」里将该 URL 填为「请求地址」。
- **URL 校验**：飞书首次配置时会发送 `type: "url_verification"`、`challenge`；扩展会原样返回 `{ "challenge": "<value>" }` 以通过校验。
- **接收消息**：订阅 `im.message.receive_v1` 后，用户/群消息会 POST 到同一 `/feishu`；扩展解析后构造 `MsgContext` 并走 `dispatchReplyWithBufferedBlockDispatcher`，回复经飞书 `im/v1/messages` 发回。
- **moltbot.json 配置示例**：

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "app_id": "飞书应用 App ID",
      "app_secret": "飞书应用 App Secret",
      "allowFrom": []
    }
  }
}
```

- **发送目标**：出站时支持 `open_id`（单聊）、`chat_id`（群聊）；入站自动根据 `event.message.chat_id` 区分群聊/单聊并选用对应 `receive_id_type` 与 `receive_id` 回发。

### 2.6 Cursor 集成配置与「配置即用」清单（阶段 3）

在 **moltbot** 的 `extensions/feishu` 中已实现 **Cursor 任务下发 + Webhook 状态回飞书**。满足以下配置后，**仅配置好即可在飞书监控 Cursor 并下发工作任务**。

**1. 飞书侧（必选）**

- 在飞书开放平台创建应用并配置事件订阅（见附录 A），`moltbot.json` 中配置 `channels.feishu`（`app_id`、`app_secret`）。

**2. Cursor 侧（必选）**

- 在 **moltbot.json** 中增加顶层 **`cursor`** 配置：
  - **`apiKey`**（必填）：Cursor Background Agents API 密钥（从 [Cursor Dashboard](https://cursor.com/agents) → Settings → Integrations → New User API Key 获取）。
  - **`webhookBaseUrl`**（推荐）：Gateway 公网访问根 URL（如 `https://gateway.example.com`），用于拼出 `webhook_url` 供 Cursor 回调；不填则启动任务时不带 webhook，无法自动收状态。
  - **`webhookSecret`**（可选）：与 Cursor 创建 agent 时填写的 webhook secret 一致，至少 32 字符，用于验签；不填则不校验签名。
  - **`feishuStatusTarget`**（推荐）：Cursor 状态更新要发到的飞书目标。格式：`open_id:xxx`（单聊）或 `chat_id:xxx`（群聊）。不填则 Webhook 仍会 200 但不会往飞书推送状态。
  - **`defaultRepository`**、**`defaultRef`**（可选）：未在飞书消息中指定仓库/分支时使用的默认值。

**3. 配置示例（moltbot.json）**

```json
{
  "channels": {
    "feishu": {
      "enabled": true,
      "app_id": "<飞书 App ID>",
      "app_secret": "<飞书 App Secret>",
      "allowFrom": []
    }
  },
  "cursor": {
    "apiKey": "<Cursor API Key>",
    "webhookBaseUrl": "https://你的Gateway公网域名",
    "webhookSecret": "<至少32字符，与 Cursor 中填写的 webhook secret 一致>",
    "feishuStatusTarget": "chat_id:oc_xxx",
    "defaultRepository": "https://github.com/org/quwoquan",
    "defaultRef": "main"
  }
}
```

**4. 使用方式**

- **下发任务**：在飞书中对机器人说「让 Cursor 做：在 quwoquan 里实现 XX 需求」或「请 Cursor 在 main 分支上修复 YY bug」。Agent 会调用 `launch_cursor_agent` 工具，向 Cursor API 发起任务；若配置了 `webhookBaseUrl`，Cursor 会在状态变化时 POST 到 `{webhookBaseUrl}/cursor-webhook`。
- **监控状态**：若配置了 `feishuStatusTarget`，任务状态（如 FINISHED、ERROR 及 PR 链接、摘要）会由扩展自动发到该飞书会话/群。

**5. 还缺什么（已补齐）**

- ✅ 飞书 ↔ Moltbot 收发（阶段 1～2）
- ✅ 飞书内下发 Cursor 任务：Agent 工具 `launch_cursor_agent`（阶段 3）
- ✅ Cursor Webhook 接收端（`/cursor-webhook`）+ 验签 + 状态推送到飞书（阶段 3）
- ✅ 配置项与文档（本节 + 附录 A）

按上述配置完成后，**无需再写代码**即可在飞书监控 Cursor 并下发工作任务。

---

## 3. 业界实践与 Cursor/Codex 能力对比（监控与指令下发）

针对「Cursor 是否像 Codex 一样有通道支持监控和指令下发」的顾虑，检索了当前业界方案与官方能力，结论如下。

### 3.1 Cursor：已有官方「监控 + 指令」通道，形态与 Codex 不同

Cursor 提供 **Background Agents API**，具备**启动任务、运行中追加指令、结果/状态回调**能力，并非“无通道”：

| 能力 | Cursor 现状 | 说明 |
|------|-------------|------|
| **指令下发** | ✅ 有 | **Launch an agent**：`POST https://api.cursor.com/v0/agents`，Body 含 `prompt.text`（自然语言任务描述）、`source.repository` / `source.ref`（仓库与分支）；可选 `prompt.images`（base64）。认证：`Authorization: Bearer $CURSOR_API_KEY`。 |
| **运行中追加指令** | ✅ 有 | **Add follow-up**：有独立 API（文档路径 `background-agent/api/add-followup`），可向已启动的 agent 发送后续 prompt，实现“运行中下发新指令”。 |
| **监控 / 状态回调** | ✅ 有 | **Webhooks**：创建 agent 时可填 webhook URL；Cursor 在 agent 状态变化时向该 URL 发送 `POST`。当前支持事件：`statusChange`（如 `ERROR`、`FINISHED`）。请求头含 `X-Webhook-Event`、`X-Webhook-ID`、`X-Webhook-Signature`（HMAC-SHA256），Body 为 JSON（含 agent id、status、仓库/分支、PR URL、变更摘要等）。 |
| **会话/对话** | ✅ 有 | **Agent conversation** 相关 API（见文档 `background-agent/api/agent-conversation`），支持与同一 agent 的对话式交互。 |

因此：**Cursor 具备“启动任务 + 运行中 follow-up + 结束/错误时 webhook 通知”的闭环**，可用于监控与指令下发；与 Codex 的差异主要在协议形态（见下），而非“有没有通道”。

### 3.2 OpenAI Codex：App Server 协议（深度集成型通道）

Codex 提供 **App Server**，面向“富客户端/自建产品”的深度集成：[Codex App Server](https://developers.openai.com/codex/app-server)。

- **协议**：双向 **JSON-RPC 2.0**，传输支持 **stdio**（默认）或 **WebSocket**（`--listen ws://IP:PORT`）。
- **抽象**：**Item**（单条输入/输出，含用户消息、工具调用、diff 等）、**Turn**（单次用户请求及 agent 工作）、**Thread**（持久会话）。
- **特点**：双向、可流式推送进度、服务端可发起请求（如审批工作流）；适合嵌入到自建 IDE/流水线中，对“每一轮交互”做细粒度控制。

与 Cursor 对比：Codex 是**长连接 + 细粒度 Item/Turn 流**；Cursor 是 **REST（启动/ follow-up）+ Webhook（结果/状态）**，更偏向“任务级”的启动与回调，而非逐条消息的 RPC 流。

### 3.3 GitHub Copilot Coding Agent：以 IM 为通道

Copilot 的 coding agent 与 **Slack、Teams** 直接集成：[Integrate with Slack](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack)，[Integrate with Teams](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-teams)。

- 在 Slack/Teams 中 @GitHub（或 @GitHub Copilot），整条 thread 作为上下文，下发任务、接收摘要、创建 PR，无需离开 IM。
- “通道”即 **Slack/Teams 会话**；监控与指令都通过同一对话完成。

对飞书的启示：若 Cursor 侧用其 **Background Agent API** 接收指令、用 **Webhook** 回写状态，则“飞书 ↔ Moltbot”可扮演类似 Slack/Teams 的角色：**人在飞书对话，Moltbot 转成对 Cursor API 的调用与 Webhook 结果的展示**。

### 3.4 业界第三方：Cursor 的 API 封装与 MCP

- **cursor-background-agent-api**（[GitHub](https://github.com/mjdierkes/cursor-background-agent-api)）：Node 客户端 + CLI + **MCP Server**，可用脚本或其它 AI 助手以 MCP 调用 Cursor Background Composer（创建任务、拉列表、查详情）。支持用 **GitHub Actions** 在 issue 创建时自动触发 Cursor agent（传 issue 标题/正文/仓库等）。说明 Cursor 的 REST + Webhook 已被用于“外部系统 → 指令下发 + 结果可见”的流水线。

### 3.5 结论与选型建议

- **Cursor 并非没有监控与指令通道**：官方提供 Launch、Add follow-up、Webhook（statusChange）、Agent conversation 等，足以实现“从飞书/其它系统下发任务 + 接收结束/错误状态”。
- **与 Codex 的差异**：Codex 是“长连接 + 细粒度 RPC 流”，适合深度嵌入；Cursor 是“REST + Webhook”，适合任务级编排与 IM/运维集成。若不需要逐 token/逐 Turn 的控制，Cursor 现有 API 即可满足“监控 + 指令下发”。
- **推荐组合**：
  - **优先用 Cursor 原生 API**：飞书/人侧需求 → Moltbot（或直接调用）→ **Cursor Background Agent API**（launch / add-followup）+ **Webhook** 接收 statusChange，在 Moltbot 或任务服务中落库/展示，飞书通过 Moltbot 查状态、下指令。
  - **Moltbot + 飞书**：作为“人机界面”与可选**任务/会话持久化**（方案 A 或 B），负责把人的话转成对 Cursor API 的调用，并把 Webhook 或轮询到的状态通过飞书回复给人。
  - 若未来需要“运行中流式进度”或更细粒度控制，可关注 Cursor 是否开放更多 streaming 或 conversation 事件，或评估 Codex App Server 类协议在自建流水线中的适用性。

---

## 4. 基于 Moltbot 监控 Cursor 在 quwoquan 的开发，并让 Cursor Agent 通过飞书查看任务与下发指令

目标：  
- **监控**：Cursor 在 quwoquan 工程上的开发行为/状态能被 Moltbot 感知并可在飞书展示。  
- **查看与下发**：人在飞书查看任务状态；通过飞书给 Cursor AI Agent 下发新指令（或 Cursor Agent 能“看到”飞书侧的状态与指令）。

### 4.1 架构思路

- **统一中枢**：Moltbot 作为“消息与任务中枢”：
  - 飞书 ↔ Moltbot（飞书通道插件，如上）。
  - Cursor / quwoquan 工程 ↔ Moltbot：通过 **Gateway API**（如 `chat.send`、`agent`、`chat.history`）或 **CLI**（`moltbot message send`、`moltbot agent`）与 Moltbot 通信。
- **任务状态存储**：需要一处双方都能读写的“任务状态”：
  - **方案 A**：用 Moltbot 的 **会话（Session）** 作为“任务/指令通道”——在飞书与某个“Cursor 专用”Agent 之间建一个会话，飞书发指令、查状态，Cursor 侧通过 Gateway 或 CLI 读同一会话并上报状态/结果。
  - **方案 B**：单独建一个**任务状态服务**（如 quwoquan 工程内的小服务或共享 DB/文档），Moltbot 与 Cursor 都读写该服务；飞书侧通过 Moltbot 的**自定义技能或 MCP 工具**查询/更新该服务；Cursor Agent 通过 MCP 或 HTTP 读写同一服务。

下面以 **方案 A（会话即任务通道）** 为主，兼顾方案 B 的扩展。

### 4.2 用 Moltbot 会话做“任务状态 + 指令”通道（方案 A）

- **专用 Agent**：在 `moltbot.json` 中为“Cursor 监控/任务”建一个 Agent（如 `cursor-tasks`），绑定到用于 Cursor 任务的工作目录（可为 quwoquan 仓库路径，仅作 Agent workspace），并配置 **bindings** 将飞书某群或某会话绑定到该 Agent。
- **飞书侧**：
  - **下发指令**：人在飞书群/单聊里 @ 机器人或发消息，如「请 Cursor 做：实现 XX 需求」→ 飞书插件把消息送入 Moltbot → 该会话的 transcript 中留下“任务/指令”。
  - **查看状态**：同一会话中由 Moltbot 回复“当前任务状态：……”；状态来源见下。
- **Cursor IDE 侧**（在本地或 CI 中，可操作任意工程如 quwoquan）：
  - **读指令**：通过 **Gateway**（若 Cursor 所在环境能连上 Moltbot Gateway）调用 `chat.history` 获取该 Agent 该 Session 的 transcript，拿到“最新或最近 N 条用户消息”作为待执行指令。
  - **写状态**：通过 **Gateway** 的 `chat.send` 或 **CLI** `moltbot message send --channel feishu --target <群/会话> --message "状态：已完成 XX"`，向同一会话发送状态更新，飞书侧即可看到。
- **实现要点**：
  - Cursor 所在环境需能访问 Moltbot Gateway（本地或内网），并持有合法认证（与 WebChat/CLI 一致）。
  - 若 Cursor 内跑的是无头脚本或 Agent，可复用 Gateway 的 `chat.send` / `chat.history` 协议，或封装成小脚本调用 `moltbot message send` / 读取 transcript 文件（若能访问 Moltbot 状态目录）。
  - 飞书里“查状态”：用户发「查一下 Cursor 任务状态」→ Moltbot 用 Agent 回复；Agent 可通过 MCP 工具或自定义技能读“任务状态源”（见方案 B），或直接读当前 Session 的 transcript 最近几条并总结回复。

### 4.3 独立“任务状态”服务（方案 B，与 Cursor 深度联动）

- **状态模型**：在 **moltbot 侧或独立小服务**（不放在 quwoquan 仓库内）定义“任务”结构，例如：`task_id`、`title`、`status`（pending/doing/done）、`assignee`（如 cursor-agent）、`last_updated`、`summary`、`detail`、可选 `repo`（如 quwoquan 仓库标识）等。
- **写入**：
  - **Cursor IDE 侧**：在 Cursor 内运行的脚本或 Agent 在关键节点（开始任务、完成步骤、报错）调用 MCP 服务或 HTTP API，更新任务状态。
  - **Moltbot 侧**：通过 MCP 工具或自定义 Skill（Skill 内调 HTTP/DB）写入同一存储，飞书里“下发新任务”时写入一条新任务记录。
- **读取**：
  - **飞书侧**：用户问「当前 Cursor 任务状态」→ Moltbot Agent 调用 MCP/技能查询任务列表或详情 → 整理成自然语言回复到飞书。
  - **Cursor IDE 侧**：在每次“拉取新指令”时，调用同一 MCP/API 获取 `status=pending` 或指定给 cursor-agent 的任务，作为本次要执行的内容。
- **对接方式**：
  - **Moltbot**：在 Agent 的 tools 中注册“任务状态”MCP 服务（或 exec 调用脚本访问 API），实现 `list_tasks`、`get_task`、`update_task`、`create_task`。
  - **Cursor IDE**：在 Cursor 规则或本地脚本中，使用同一 MCP 或同一 HTTP API，实现读待办 / 更新状态（**不修改 quwoquan 仓库代码**，仅 Cursor 侧配置或独立脚本）。

这样，**飞书 ↔ Moltbot** 负责人机对话与查状态/下指令；**Moltbot ↔ 任务服务** 与 **Cursor IDE ↔ 任务服务** 共享同一数据源，实现监控与指令下发；任务服务与实现均在 moltbot/独立服务侧，不涉及 quwoquan 仓库。

### 4.4 简要流程串联

1. **人在飞书**：「请 Cursor 做：在 quwoquan 里实现 XX 需求」  
   → 飞书插件 → Moltbot（feishu 通道）→ dispatch → 可选：写入“任务状态服务”一条新任务（方案 B），或仅作为会话消息（方案 A）。
2. **Cursor Agent（在 quwoquan 工程）**：  
   - 定时或触发时：通过 Gateway `chat.history` 或 任务 API 拉取“待办指令”；  
   - 执行开发（编辑、运行测试等）；  
   - 更新状态：Gateway `chat.send` 或 任务 API 写入“进行中/已完成/失败+摘要”。
3. **人在飞书**：「查一下 Cursor 任务状态」  
   → Moltbot Agent 通过会话历史或 MCP/任务 API 汇总 → 回复「当前任务：XX，状态：进行中/已完成，……」。

### 4.5 小结：监控 + 飞书查看 + 下发指令

- **监控 Cursor 在 quwoquan 的开发**：由 Cursor 侧在关键节点向“任务状态”或 Moltbot 会话写入状态；Moltbot 不直接“监控 Cursor 进程”，而是**消费 Cursor 主动上报的状态**。
- **飞书查看任务状态**：通过飞书与 Moltbot 对话，Moltbot Agent 从会话或任务服务中读取并回复状态。
- **飞书下发新指令**：人在飞书发消息作为新任务/指令；Cursor 通过 Gateway 或任务 API 拉取并执行，实现“Cursor AI Agent 通过飞书接收并执行指令”。

### 4.6 基于 Cursor 官方 API 的集成方式（推荐优先）

在「飞书 ↔ Moltbot」之上，可直接对接 **Cursor Background Agents API**，减少对“Cursor 读 Moltbot 会话”的依赖：

- **下发指令**：人在飞书说「让 Cursor 做：实现 XX 需求」（可注明仓库如 quwoquan）→ Moltbot 收到后，由 **moltbot 侧** 后端或 Skill 调用 `POST https://api.cursor.com/v0/agents`，Body 中 `prompt.text` 为需求描述，`source.repository` 为目标仓库 URL（如 quwoquan），`source.ref` 为分支；可选在创建时传入 **webhook_url** 指向 Moltbot 提供的 Webhook 端点。
- **监控状态**：Cursor 在 agent 结束或报错时向 webhook 发送 `statusChange`（含 agent id、status、PR URL、变更摘要）。**接收端在 moltbot 侧**（或与 Moltbot 对接的服务）验证签名、落库，并可选通过 Moltbot 推一条消息到飞书（如「Cursor 任务已结束：成功/失败，PR：…」）。
- **运行中追加指令**：若需在 agent 运行中加需求，由 **moltbot 侧** 调用 Cursor 的 **Add follow-up** API（传入 agent id 与新 prompt），无需 Cursor 主动轮询 Moltbot。

这样，**监控与指令下发都走 Cursor 官方通道**，实现全部在 **moltbot + 飞书扩展** 侧；飞书 + Moltbot 负责人机界面与任务列表/历史展示。**不涉及对 quwoquan 仓库的修改**。

---

## 5. 实施顺序建议

1. **更新 Moltbot 代码**：按 1.2 选一种方式与 GitHub 同步。
2. **飞书扩展**：在 moltbot 中实现 `extensions/feishu`（收消息 → dispatch，出站 → 飞书 API），并在配置中启用 feishu 通道与 bindings。
3. **验证 QA 技能**：在飞书与 Moltbot 对话，提问华为云/知识库类问题，确认 huawei-cloud-qa 等技能被正常调用。
4. **Cursor 监控与指令**：**优先采用 4.6 节**，用 Cursor Background Agents API（launch + webhook + add-followup）做指令下发与状态监控，Moltbot/飞书做人机界面与状态展示；可选再叠加方案 A（会话）或方案 B（任务服务）做统一任务列表与对话式查询。

---

## 附录 A：在飞书上创建此应用的详细指导

以下步骤用于在飞书开放平台创建**企业自建应用**，获取 **App ID**、**App Secret**，并配置**事件订阅**与**机器人权限**，使 Moltbot 的 `extensions/feishu` 能接收飞书消息并回复。请使用**企业管理员或具备应用创建权限**的飞书账号操作。

### A.1 创建企业自建应用

1. **登录飞书开放平台**  
   浏览器打开：<https://open.feishu.cn/app>（或从 <https://open.feishu.cn> 进入「开发者后台」）。

2. **创建应用**  
   - 点击 **「创建企业自建应用」**。  
   - 填写 **应用名称**（如「Moltbot 机器人」）、**应用描述**（可选）、**应用图标**（可选）。  
   - 创建完成后，进入该应用的详情页。

3. **获取凭证**  
   - 左侧菜单进入 **「凭证与基础信息」**。  
   - 记录 **App ID** 和 **App Secret**（App Secret 仅展示一次，请妥善保存；若已丢失，可重置后重新获取）。  
   - 后续在 `moltbot.json` 的 `channels.feishu` 中填写 `app_id` 与 `app_secret`。

### A.2 添加机器人能力并配置使用范围

1. **启用机器人**  
   - 左侧菜单进入 **「应用功能」→「机器人」**。  
   - 开启 **「启用机器人」**。

2. **配置使用范围（可选）**  
   - 在机器人配置中可设置 **「可用范围」**：全部员工、指定成员或指定部门。  
   - 按需选择，确保要使用机器人的用户/群在范围内。

3. **权限与能力（接收与发送消息）**  
   - 在 **「权限管理」** 中申请以下权限（具体名称以控制台为准，一般为「以应用身份」类）：  
     - **接收消息**：  
       - 获取用户发给机器人的单聊消息（单聊必选）。  
       - 获取群组中所有消息，或「获取用户在群组中 @ 机器人的消息」（按需二选一或都选）。  
     - **发送消息**：  
       - 以应用身份发消息（调用 `im/v1/messages` 所需）。  
   - 部分权限为「免审」可立即生效；若为「需审核」权限，需在 **「版本管理与发布」** 中创建版本并提交审核，通过后生效。

### A.3 配置事件订阅（Webhook 请求地址）

1. **进入事件订阅**  
   - 左侧菜单进入 **「事件与回调」** 或 **「事件订阅」**。

2. **选择订阅方式**  
   - 选择 **「将回调发送至开发者服务器」**（即 Webhook 方式）。

3. **填写请求地址**  
   - **请求地址**填写：`https://<你的公网域名或 IP>/feishu`。  
   - 其中 `<你的公网域名或 IP>` 为运行 Moltbot Gateway 且可被飞书访问的地址（如 `gateway.example.com` 或带端口的 `ip:port`，需使用 HTTPS；本地开发可用内网穿透工具暴露 HTTPS 地址）。  
   - 飞书要求该地址为 **公网可访问**；保存时飞书会向该 URL 发送 **URL 校验** 请求。

4. **通过 URL 校验**  
   - 飞书会向请求地址发送一次 **POST**，Body 为 JSON：`{"type":"url_verification","challenge":"<随机字符串>"}`。  
   - Moltbot 的 feishu 扩展会**自动**返回 `{"challenge":"<同一字符串>"}`，无需额外配置。  
   - **前提**：保存请求地址前，Gateway 已启动且 `/feishu` 可被飞书公网访问，否则校验会失败。  
   - 校验成功后，请求地址即可保存。

5. **添加事件**  
   - 在事件订阅配置中点击 **「添加事件」**。  
   - 在「消息与群组」或「接收消息」相关分类下，勾选 **「接收消息 v2.0」** 对应事件（事件类型一般为 `im.message.receive_v1`）。  
   - 保存后，用户或群组发给机器人的消息会 POST 到上述 `/feishu` 地址。

6. **加密方式（可选）**  
   - 若未配置 **Encrypt Key**，飞书发送的即为明文 JSON（本扩展当前按明文处理）。  
   - 若在「事件与回调」中配置了 **Encrypt Key**，需在扩展中增加解密逻辑后再解析；当前 feishu 扩展**未实现解密**，建议先不启用加密以便通过校验和收消息。

### A.4 发布与使用

1. **发布应用**  
   - 若申请了需审核权限：进入 **「版本管理与发布」**，创建新版本并 **「申请发布」**，等待企业管理员审批。  
   - 仅使用免审权限时，部分环境下无需发布即可在「可用范围」内使用；若无法收到消息，再检查是否需提交发布。

2. **将机器人加入会话**  
   - **单聊**：在飞书客户端中搜索该应用/机器人名称，发起单聊即可。  
   - **群聊**：在目标群组中点击「设置」→「群机器人」→「添加机器人」→ 选择刚创建的应用，添加后群成员即可 @ 机器人或（若开通了「群组中所有消息」）直接发消息由机器人接收。

3. **验证**  
   - 确保 Moltbot Gateway 已启动，且 `moltbot.json` 中已配置 `channels.feishu` 的 `app_id`、`app_secret`。  
   - 在飞书中向机器人发一条文本消息；若配置正确，Moltbot 会处理并经由 feishu 扩展调用飞书 API 将回复发回该会话。

### A.5 常见问题

| 现象 | 可能原因 | 处理建议 |
|------|----------|----------|
| URL 校验失败 | Gateway 未启动或 `/feishu` 无法被飞书公网访问 | 确保 Gateway 运行且请求地址为 HTTPS、公网可达；可用 curl 自测 `POST /feishu` 带 `{"type":"url_verification","challenge":"test"}` 是否返回 `{"challenge":"test"}`。 |
| 收不到消息 | 未订阅 `im.message.receive_v1` 或权限未生效 | 检查事件订阅中已添加「接收消息 v2.0」；检查权限已申请并通过审核（若需审核）。 |
| 机器人不回复 | `app_id`/`app_secret` 错误或未配置 | 核对「凭证与基础信息」与 `moltbot.json` 中 `channels.feishu` 一致；查看 Gateway 日志是否有 feishu 相关报错。 |
| 群内需 @ 才回复 | 只开通了「@ 机器人的消息」 | 若希望群内任意消息都回复，在权限中申请「获取群组中所有消息」并发布新版本。 |

更多细节请以飞书官方文档为准：  
- [飞书开放平台](https://open.feishu.cn/document)  
- [机器人概览](https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/bot-v3/bot-overview)  
- [接收消息（事件）](https://open.feishu.cn/document/server-docs/im-v1/message/events/receive_message)（文档路径可能随版本调整，可在站内搜索「接收消息」「事件订阅」）。

---

## 6. 参考

**Moltbot**
- Moltbot 设计：`moltbot/docs/MOLT-DESIGN.md`
- 通道与路由：`moltbot/docs/concepts/channel-routing.md`
- Gateway RPC：`moltbot/src/gateway/server-methods/chat.ts`（`chat.send`、`chat.history`）
- Slack 扩展结构：`moltbot/extensions/slack/index.ts`、`extensions/slack/src/channel.ts`
- 技能与 exec：`moltbot/skills/huawei-cloud-qa/SKILL.md`、`moltbot/src/agents/huawei-cloud-prompt.ts`

**飞书**
- 飞书开放平台：<https://open.feishu.cn/document>
- 机器人概览：<https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/bot-v3/bot-overview>

**Cursor 官方（监控与指令）**
- Background Agents API 总览：<https://docs.cursor.com/en/background-agent/api/overview>
- Launch an agent：<https://docs.cursor.com/en/background-agent/api/launch-an-agent>
- Add follow-up：<https://docs.cursor.com/en/background-agent/api/add-followup>
- Webhooks（statusChange）：<https://docs.cursor.com/en/background-agent/api/webhooks>
- Agent status：<https://docs.cursor.com/en/background-agent/api/agent-status>
- Agent conversation：<https://docs.cursor.com/en/background-agent/api/agent-conversation>

**Codex / Copilot 对比**
- Codex App Server（JSON-RPC/WebSocket）：<https://developers.openai.com/codex/app-server>
- Copilot 与 Slack 集成：<https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack>
- Copilot 与 Teams 集成：<https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-teams>

**第三方**
- Cursor Background Agent API 客户端（CLI + MCP）：<https://github.com/mjdierkes/cursor-background-agent-api>
- 使用示例与请求格式：<https://aiengineerguide.com/blog/cursor-background-agents-api/>
