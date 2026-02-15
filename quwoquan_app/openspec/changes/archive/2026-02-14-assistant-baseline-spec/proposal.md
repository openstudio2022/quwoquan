## Why

小趣私人助手是产品的核心差异能力，但目前缺少一份独立、稳定的功能基线规格：入口形态（全屏/半屏/直接会话）、与浏览上下文的结合方式、以及浏览信息的存储与使用均未在规格层统一描述。将「小趣私人助手」单独建立为重大特性并产出基线功能规格，便于后续在 OpenSpec 上持续补充（如统一交互协议、帮读/任务抽屉、主动触发等），避免与欢迎页、发现页等变更耦合。

## What Changes

- 建立小趣私人助手**基线能力规格**：覆盖浏览信息本地存储与云端同步预留、打开小趣时的**半弹窗**形态与内容、记录时机与入口统一。
- 定义**浏览信息**数据模型与存储：VisitTarget（页面型/实体型）、VisitRecord（首次/再次/常用等衍生体验等级）、单 box 本地存储与 VisitRecorderService 封装；云端仅定义 VisitSyncService 接口与数据契约，不实现具体同步。
- 定义**小趣打开形态**：所有入口统一先展示半弹窗（约 50% 屏高），传入 AssistantOpenContext（来源、tab/实体、VisitTarget、experienceLevel、可选 hints）；半弹窗含上下文欢迎、推荐 chips、「当前适合干啥」、输入框与「进入完整对话」；进入完整对话时关闭半弹窗并 push 会话页并携带 context。
- 明确**记录时机**：发现/圈子/作者/圈子主页/创作等关键页面在进入时解析 VisitTarget 并调用 recordVisit；同一 target 5 分钟内去重。
- 明确**入口契约**：所有「打开小趣」入口改为先调半弹窗（传入 AssistantOpenContext），不再直接 push 助理主页或会话页。

## Capabilities

### New Capabilities

- `assistant-baseline`: 小趣私人助手基线功能规格。包含：浏览信息模型（VisitTarget/VisitRecord）与本地存储（VisitRecorderService、Hive）、云端同步预留（VisitSyncService 接口与数据契约）；打开小趣的入口形态（半弹窗优先、AssistantOpenContext、欢迎句/chips/当前适合干啥/进入完整对话）；各场景记录时机与去重规则；全局入口统一为「先半弹窗再可选进入完整对话」。

### Modified Capabilities

- （无。基线为新增能力，与现有 `profile-xiaoqu`、`chat` 等可并存；后续变更可再调整相关 spec。）

## Impact

- 受影响规格：新增 `openspec/specs/assistant-baseline/spec.md`，作为小趣私人助手特性的单一事实来源，后续迭代在该 spec 或关联 delta 上扩展。
- 受影响实现范围（实施阶段）：`lib/core/services/`（visit_recorder_service、visit_sync_service 抽象）、`lib/features/assistant/`（context、widgets 半弹窗、config 欢迎与 chips）、各入口页与路由（发现/圈子/作者/圈子主页/创作/聊天/我的等改为先半弹窗）、`main.dart` 或初始化处 Hive box 注册。
- 非目标：本变更仅产出基线规格与实现任务，不包含欢迎页/发现页 IA 升级、帮读卡/任务抽屉/多形态切换等，留待后续 change 在基线之上补充。
