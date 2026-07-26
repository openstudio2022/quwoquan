# L2 Business Capability：内容类型框架 (`content-type-framework`)

> 所属领域：[`discovery-content`](../spec.md)
>
> 设计归属：[本层 design.md](./design.md)

## 1. 能力目标

为 `content_feed` 中的微趣、图片、视频和文章提供统一内容身份与呈现模型，并通过类型扩展表达差异而不拆分事实表或业务场景。

## 2. 范围与非目标

### In Scope

- 由本目录 Story 组合交付“content-type-framework（内容类型通用框架）”的独立业务结果。

### Out of Scope

- 其他 L2 的事实所有权、metadata schema 与实现施工步骤。

## 3. Journey / Scenario 贡献

- [`JNY-004 / SCN-001`](../../spec.md#scn-001)
  - 本能力处理：组合本目录 Story 的可观察行为。
  - 本能力输出：**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景，并将可观察结果交给下游。
  - 失败时终态：可解释、可恢复且不伪造成功。

## 4. Story



- [`creation-mode-and-surface-ia-unification`](./creation-mode-and-surface-ia-unification/spec.md)：用户只需要在入口选择开始动作，系统能根据真实媒体结果进入图片或视频编辑状态，且发布 payload 的 `contentType` 与最终媒体类型一致。
- [`creation-tagging-ia`](./creation-tagging-ia/spec.md)：各类型编辑页提供可选标签，未选择标签不得阻断发布。
- [`markdown-article-kernel`](./markdown-article-kernel/spec.md)：小屏或可访问性大字号下统一降级为 `fullWidth`。
- [`unified-presentation-model`](./unified-presentation-model/spec.md)：retired_terms / dart_semantic / mock_isolation 门禁绿，app 门禁无 FAIL/BLOCK。

## 5. 能力要求

<a id="req-001"></a>
### REQ-001 content type framework 能力 SIT

- 本能力必须组合直属 Story 与公开契约，交付“**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景”所定义的业务结果；失败终态必须可区分且不得伪造成功。

<a id="req-002"></a>
### REQ-002 结论：content_feed 应当做媒体类型区分（标签、特征、运营可差异化），但基于**统一 Post 聚合 + contentType 判别**，通用框架保证共性，各类型在标签/特征/运营上按需扩展

- **结论**：content_feed 应当做媒体类型区分（标签、特征、运营可差异化），但基于**统一 Post 聚合 + contentType 判别**，通用框架保证共性，各类型在标签/特征/运营上按需扩展。

## 6. 契约与依赖

- 上游能力：[`discovery-content`](../spec.md) 声明的领域入口。
- 下游能力：本目录直接 Story 及其公开结果。
- 一致性要求：遵循本层或父 L1 DEC 声明的一致性边界。

## 7. 集成验收

<a id="sit-001"></a>
### SIT-001 content type framework 能力 SIT

- GIVEN 执行“content type framework 能力”所需的身份、输入与上游事实均有效。
- WHEN 参与者发起“content type framework 能力”对应动作。
- THEN 直属 Story 共同交付“**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景”，失败终态可区分且不产生伪成功事实。

## 8. 开放事项

<a id="open-001"></a>
### OPEN-001 content type framework 能力 SIT

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：**定位**：content_feed 场景下对四种媒体类型（微趣 micro、图片 image、视频 video、文章 article）的通用内容模型与按类型扩展的约定，不拆表、不拆场景。
- 完成判定：`SIT-001` 对应行为满足且真实测试 `spec_ref` 有效
