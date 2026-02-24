# Moltbot + 飞书 + Cursor IDE 开发计划（独立于 quwoquan）

> **开发范围**：仅 **moltbot** 与 **Cursor IDE** 的集成及飞书通道；**不涉及 quwoquan 仓库**的任何开发任务。  
> **目标**：通过飞书监控 Cursor IDE 中的开发状态（例如在 quwoquan 上的开发），并向 Cursor IDE 获取与下发开发任务。

---

## 1. 范围与目标（再次明确）

| 项目 | 说明 |
|------|------|
| **在做的** | moltbot 飞书扩展、飞书 ↔ Moltbot 消息收发、可选 QA 技能；Cursor IDE 侧任务获取与状态上报（Gateway/CLI 或 Cursor API）；飞书内查看状态与下发任务。 |
| **不在做的** | quwoquan 仓库内任何代码、配置、runtime、特性树、契约或测试。quwoquan 仅作为「被 Cursor 开发的工程」这一**对象**。 |

**验收目标**：
- 人在飞书能与 Moltbot 对话（含可选 QA 技能）。
- 人在飞书可查看「Cursor IDE 任务状态」、可下发「新开发任务」给 Cursor IDE。
- Cursor IDE 侧能获取任务并上报状态（通过 Moltbot Gateway/CLI 或 Cursor Background Agents API）。

---

## 2. 阶段划分与自动化验证

### 阶段 1：Moltbot 代码与飞书扩展底座（仅 moltbot 仓库）

**目标**：moltbot 从 GitHub 可更新；飞书通道扩展存在且可加载，收/发消息打通。

**交付物**：
- 从 GitHub 更新/克隆 moltbot 的步骤可执行（见 `moltbot-feishu-cursor-integration.md` §1）。
- 在 **moltbot 仓库** 中新增 `extensions/feishu`：
  - `package.json`（moltbot.extensions 入口）、`index.ts`（registerChannel feishu）。
  - 入站：飞书事件（长连接或 Webhook）→ 解析 `im.message.receive_v1` → 构造 MsgContext → 调用 dispatch。
  - 出站：实现 `ChannelPlugin.outbound`（sendText/sendMedia），调飞书 `im/v1/messages`。
  - 配置：`moltbot.json` 中 `channels.feishu`（app_id、app_secret、verification_token 等）。

**自动化验证**（全部在 moltbot 仓库内）：
```bash
cd /path/to/moltbot
pnpm install
pnpm build
pnpm test
# 扩展被正确加载（如 pnpm moltbot channels 或启动 gateway 后列表含 feishu）
```

**验收清单**：
- [ ] `pnpm build` 零错误
- [ ] `pnpm test` 通过
- [ ] 飞书扩展出现在通道列表或 gateway 可加载
- [ ] 飞书应用配置完成后，收一条消息能在 Moltbot 侧收到并可选回复（人工或脚本验证一次）

---

### 阶段 2：飞书内对话与可选 QA 技能（仅 moltbot）

**目标**：在飞书与 Moltbot 对话可用；若启用 huawei-cloud-qa 等技能，在飞书中提问能走技能并得到回复。

**交付物**：
- 飞书 ↔ Moltbot 双向消息稳定（SessionKey、路由、多会话隔离正确）。
- 可选：在对应 workspace 启用技能后，飞书提问触发 exec 调用 run.sh 并回复。

**自动化验证**：
```bash
cd /path/to/moltbot
pnpm build && pnpm test
# 契约/集成：若有飞书 mock 或 sandbox 测试，加入 CI
```

**验收清单**：
- [ ] 飞书发消息 → Moltbot 有回复
- [ ] 可选：飞书问华为云/知识库问题 → 回复来自 huawei-cloud-qa 等技能
- [ ] 无 quwoquan 仓库改动

---

### 阶段 3：Cursor IDE 任务获取与状态上报（moltbot + Cursor 侧配置/脚本）

**目标**：Cursor IDE 能「拉取待办任务」并「上报状态」；飞书侧能查看状态、下发新任务。

**方案选型**（二选一或组合）：
- **A：Moltbot 会话**  
  Cursor 侧通过 Gateway `chat.history` 拉取“用户最新消息”作为任务，通过 `chat.send` 或 `moltbot message send --channel feishu` 上报状态；飞书侧在同一会话查看与下发。
- **B：Cursor Background Agents API**  
  Moltbot 侧（Skill 或后端）调用 Cursor API 创建 agent（prompt + source.repo），并配置 webhook；Cursor 完成后回调 webhook，Moltbot 将结果推到飞书。

**交付物**：
- **若选 A**：在 **moltbot 仓库** 提供文档或示例脚本（不放在 quwoquan 内），说明 Cursor 侧如何调 Gateway/CLI 拉任务、发状态；飞书专用 Agent + Session 配置说明。
- **若选 B**：在 **moltbot 仓库** 实现 Webhook 接收端（验签、落库或转会话）+ 调用 Cursor Launch/Add follow-up API 的 Skill 或脚本；飞书内展示状态/下发任务的交互方式文档或简单 UI 文案。

**自动化验证**：
```bash
cd /path/to/moltbot
pnpm build && pnpm test
# 若有 Webhook 接收端：单元测试或 mock 请求测试验签与落库
```

**验收清单**：
- [x] Cursor 侧能获取到“待办任务”（通过 Moltbot 会话或 Cursor API 创建出的任务）— 已实现：飞书发指令 → Agent 调用 `launch_cursor_agent` → Cursor API 创建任务
- [x] Cursor 侧能上报状态（会话中可见或 Webhook 处理后飞书可见）— 已实现：`/cursor-webhook` 接收 Cursor 回调并推送到 `cursor.feishuStatusTarget`
- [x] 人在飞书能下发新任务、能查当前任务状态 — 已实现：下发通过对话 + 工具；状态通过 Webhook 推飞书
- [x] 实现与代码仅在 moltbot（及可选独立服务）侧，**无 quwoquan 仓库改动**

---

### 阶段 4：端到端验收与文档（不涉及 quwoquan）

**目标**：飞书 → 监控 Cursor 开发状态 + 向 Cursor 下发任务，整条链路可演示、可文档化。

**交付物**：
- 端到端流程说明（飞书发任务 → Cursor 执行/上报 → 飞书查状态）。
- 可选：在 Cursor 中打开 **任意** 工程（例如 quwoquan）执行一条“来自飞书”的任务并上报，作为验收演示；**仍不修改 quwoquan 仓库**。

**自动化验证**：
- 同阶段 1～3 的 build/test；无新增 quwoquan 代码或配置。

**验收清单**：
- [ ] 文档完整，他人可按文档在飞书完成「查状态 + 下任务」、在 Cursor 完成「拉任务 + 报状态」
- [ ] 演示可选用 quwoquan 作为被开发仓库，但**不提交任何对 quwoquan 的改动**

---

## 3. 执行顺序与原则

1. **只改 moltbot（及可选独立服务）**：所有开发、测试、脚本、配置均在 moltbot 仓库或独立小服务中完成。
2. **quwoquan 仅作“被开发对象”**：文档与演示中可以写「在 Cursor 中打开 quwoquan 并执行任务」，但不为 quwoquan 增加代码、规则或任务。
3. **每阶段以自动化验证通过为完成**：阶段 1～4 的 `pnpm build`、`pnpm test` 及所列验收清单通过后，该阶段方可验收。

---

## 4. 参考文档

- 方案与 API 细节：`docs/moltbot-feishu-cursor-integration.md`
- Moltbot 设计：moltbot 仓库内 `docs/MOLT-DESIGN.md`
- Cursor Background Agents API：<https://docs.cursor.com/en/background-agent/api/overview>
- 飞书开放平台：<https://open.feishu.cn/document>
