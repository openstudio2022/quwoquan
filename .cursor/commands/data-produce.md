---
name: /data-produce
id: data-produce
category: Workflow
description: 数据工程 · 内容润色生成阶段
---

# data-produce

> fanout 模式下，本命令降为 **per-ref worker 步骤**：一个 Subagent 消费 `qwq-data object-queue lease-next` 返回的单 ref lease packet（含执行合约 + Ralph 出口门），只处理自己租到的 ref，完成后 `object-queue complete`。单模式仍按下文整批走。

## 命令目的
基于下载源润色生成可发布内容。单命令完成 compose + review。

## 输入
- `--task {taskId}` `--batch {batchId}` `--type {article|image|moment|video}`
- sources/{entityName}/（来自 download）
- entities/{领域}/{类型}/{名称}/（来自 build，作为全局上下文）
- sop/{type}.md + sop/主页/{领域}/{类型}/（内容策略）

## 目录结构

posts 按内容角度标签分类，标题命名目录，编号子目录：
```
posts/article/内容角度/攻略/峨眉山攻略指南/1/
  article.md
  manifest.json
  assets/
```

## 内容角度与实体类型对应

| 实体类型 | 建议内容角度 |
|---|---|
| 景区/遗址/古镇 | 攻略/体验/文化 |
| 打卡地 | 攻略/日记 |
| 博物馆 | 文化/体验 |
| 美食街/餐厅 | 探店/攻略 |
| 学校 | 攻略/体验 |
| 赛事 | 体验/攻略 |

## agent 执行

### compose
1. 基于 sop 模板 + 高质量源润色生成 article.md
2. 含 asset:// 图片引用（fullWidth / wrapLeft / wrapRight）
3. 含 /entity/{领域}/{类型}/{名称} 引用（三层路径）
4. 含 /tag/{tagPath} 引用

### review（ReAct 质量归因）
交叉校验内容质量与引用一致性，过三门（生成者出处 / 模板指纹 / 出处改写）+ 事实门
（must-include facts / 数值可溯源）。质量欠佳时**先归因再回退到对应阶段**，不要原地反复重写：

| 归因 | 判据 | 回退动作 |
|---|---|---|
| 证据不足 | retained 源 < 2、质量普遍 C/Reject、事实门 must-include 缺失 | 回 `/data-download` ReAct 第 3 步：换更具体检索词再检索/补权威源 |
| 模板/SOP 失配 | 源充足但版式/结构/风格不达 SOP 标准、指纹门告警 | 调整路由模板 / SOP few-shot（不改源），重走 compose |
| 创作执行问题 | 源与模板均达标但成稿跑题/啰嗦/引用错 | 同模板重写 article.md |

每次「证据是否充足 / 质量归因 / 回退决策」经 `/data-reflect` 记入 run 反思账本，
沉淀到 `notes.md`，并由 `task resume` 下次加载，加速同类任务。

## manifest.json（无 topicId）
```json
{
  "contentType": "article",
  "title": "峨眉山攻略指南",
  "entityRefs": ["地点/景区/峨眉山"],
  "tagRefs": ["主题/佛教文化", "内容角度/攻略"],
  "sourcePaths": ["sources/峨眉山/content/source_01.md"],
  "assets": ["峨眉山_攻略_cover.jpg"],
  "createdAt": "...",
  "updatedAt": "..."
}
```

## 准出
- 每篇 > 600 字
- 含 asset:// + /entity/ + /tag/
- entityRefs 格式 `{领域}/{类型}/{名称}`（三层）
- manifest 无 topicId

自然语言等价触发：用户直接描述与本命令目标相同的需求时，也按 `/data-produce` 语义执行；执行前仍需按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection，完成后按 Exit Review 收口。

协议补充：执行前按 `docs/agent_context_contract.md` 完成 Spec Entry / Pre-work Reflection；完成后按 Exit Review 输出证据、门禁结果与剩余风险。
