## Why

当前产品已具备「兴趣内容 + 圈子 + 社交」基础，但小趣在不同页面的入口与交互形态分散，用户心智不统一，难以形成“由私人助理编排体验”的核心差异。需要先在欢迎页与发现页建立统一、简洁、可感知的小趣交互基线，为后续全站升级提供稳定框架。

## What Changes

- 将欢迎页在不大改版式的前提下升级为“兴趣圈 + 小趣陪伴”叙事，采用单主句策略并引入小趣轻量形象与语义。
- 重构发现页一级信息架构为「帮读 / 美图 / 视频」，将微趣与文章在体验层合并为“小趣帮读”。
- 建立小趣统一交互协议 V1：单一全局唤起动作、三种交互形态（帮读卡/任务抽屉/会话页）、六类命令式动作（读/记/办/发/找/排）。
- 规范小趣主动触发边界与反馈闭环，确保“无处不在但不过度打扰”。
- 明确阶段范围：圈子、创作、趣聊、小趣主页、我的等全面升级能力作为遗留事项进入后续迭代。

## Capabilities

### New Capabilities

- `assistant-interaction-layer`: 定义小趣在全局、发现页与会话场景中的统一入口、形态切换、命令式与主动式交互协议。

### Modified Capabilities

- `welcome-auth`: 欢迎页文案与轻量视觉叙事升级，突出“你的兴趣圈，有小趣陪你”并维持现有页面骨架。
- `discovery-feed`: 一级分类与内容编排升级为「帮读 / 美图 / 视频」，新增帮读聚合与简报式交互规则。

## Impact

- Affected specs: `openspec/specs/welcome-auth/spec.md`, `openspec/specs/discovery-feed/spec.md`, 新增 `openspec/specs/assistant-interaction-layer/spec.md`。
- Affected product surfaces: 欢迎页、发现页顶部结构、发现流内容类型映射、小趣全局入口与发现内交互组件。
- Affected code scope (implementation phase): `lib/features/welcome/pages/welcome_screen.dart`, `lib/features/home/pages/discovery_page.dart`, `lib/components/assistant_floating_ball.dart`, 以及与小趣入口相关的共享组件与常量。
- Non-goals in this change: 圈子、创作、趣聊、小趣主页、我的页的深度改造仅记录为后续任务，不在本次实施范围内。
