---
name: /data-reflect
id: data-reflect
category: Workflow
description: 数据工程 · ReAct 反思账本（自学习沉淀）
---

# data-reflect

## 命令目的
把每轮跑数中「证据是否充足 / 质量归因 / 回退决策」沉淀为可复用经验，形成自学习飞轮。
不新增脚本，复用 `qwq-data task record-run` / `task resume`（单一沉淀位 = run.json + notes.md）。

## 何时记（ReAct 关键决策点）
- **download** 后：证据充足性判定（retained 源是否 ≥2、质量分布）。
- **produce review** 后：质量归因三分支（证据不足 / 模板·SOP 失配 / 创作执行问题）及回退决策。
- 出现无法当轮解决的缺口：记入 `openGaps`，下次 `resume` 优先处理。

## 记什么（每条反思 = query + 归因 + 决策）
| 字段 | 含义 | 例 |
|---|---|---|
| query | 本轮检索词/问题 | `稻城亚丁 牛奶海 海拔 最佳季节` |
| attribution | 质量归因 | `证据不足` / `模板·SOP 失配` / `创作执行问题` |
| decision | 回退/调整决策 | `换更具体检索词补权威源，重走 download` |

## 怎么记
```bash
qwq-data task record-run <taskId> \
  --owner you --summary "稻城亚丁标杆：source 偏少" \
  --reflect-query "稻城亚丁 牛奶海 海拔 最佳季节" \
  --reflect-attribution "证据不足" \
  --reflect-decision "换检索词补百科+游记，retained 升至3" \
  --open-gap "地点/景区/牛奶海 待补主页" \
  --entities-added 1 --posts-added 3 --mark-done 地点/景区/稻城亚丁
```
- 写入 `runs/run_*.json` 的 `reflections[]`，追加到 `notes.md`「反思账本」段，缺口进 `progress.openGaps`。

## 怎么加载（下次提速）
```bash
qwq-data task resume <taskId>
```
- 打印缺口 + `openGaps` + **近 3 条过往反思**（归因→决策），同类任务直接复用，避免重复踩坑。

## 飞轮闭环
检索不足→换词再检索；模板失配→调路由/结构质量契约；执行问题→重写。
反复出现的同类归因 → 升级为 SOP / 模板 / 质量门改进（大循环），而非每轮临时绕过。

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-reflect` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
