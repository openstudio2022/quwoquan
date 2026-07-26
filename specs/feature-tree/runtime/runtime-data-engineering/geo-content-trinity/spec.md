# L3 Story：主页、文章、图片和视频复用同一 execution、来源权利与发布闭 (`geo-content-trinity`)

> 所属能力：[`runtime-data-engineering`](../spec.md)
>
> Journey / Scenario：[`JNY-001 / SCN-004`](../../../spec.md#scn-004)
>
> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为开发、测试或运维角色，我希望主页、文章、图片和视频复用同一 execution、来源权利与发布闭包，从而让调用方获得稳定结果，并让维护者能够定位和恢复失败。

## 2. 范围与非目标

### In Scope

- 四类内容的单 execution 五阶段结构。
- source unit、图片权利、creator/tag/entity 引用与 review 闭包。
- 失败对象隔离和成功对象独立发布。

### Out of Scope

- 按站点建立第二套 runner 或发布目录。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 多内容类型复用同一来源与权利合同

- 图片来源、下载字节、授权与发布引用均可回放。

<a id="req-002"></a>
### REQ-002 失败对象隔离与成功对象独立发布

- release-first ship 与 operator journey 契约通过。

## 4. 契约引用

- canonical：`quwoquan_data/verticals/<vertical>/providers.yaml`
- canonical：`quwoquan_data/verticals/travel/rights/license_policy.yaml`
- canonical：`quwoquan_data/scripts/content/release/canonical/gate.py`
- canonical：`quwoquan_data/scripts/content/review/publish_filter.py`

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 多内容类型复用同一来源与权利合同

- GIVEN recipe 明确 contentType，来源与权利规则来自静态 registry。
- WHEN execution 执行 download、quality、compose、draft、review。
- THEN 四类内容均使用相同 source unit、Agent 审计与逐图权利闭包。
- THEN 中间文件只进入 execution，approved 对象才进入 publish/release。

<a id="gwt-002"></a>
### GWT-002 失败对象隔离与成功对象独立发布

- GIVEN 同一 execution 中部分对象在来源、质量、权利或 review 门失败。
- WHEN 生成 canonical publish 与 immutable release。
- THEN release 只包含 approved 对象，失败对象保留在 execution evidence。
- THEN 下游不得看到悬挂 entity、creator、tag 或 media 引用。

## 6. 依赖

- 前置要求：[`runtime-data-engineering`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 多内容类型复用同一来源与权利合同

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：图片来源、下载字节、授权与发布引用均可回放。
- 完成判定：`GWT-001` 对应行为满足且真实测试 `spec_ref` 有效

<a id="open-002"></a>
### OPEN-002 失败对象隔离与成功对象独立发布

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺实现或直接 `spec_ref`；目标：release-first ship 与 operator journey 契约通过。
- 完成判定：`GWT-002` 对应行为满足且真实测试 `spec_ref` 有效
