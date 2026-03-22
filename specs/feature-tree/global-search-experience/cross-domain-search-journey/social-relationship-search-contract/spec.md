# L3 Scenario: social-relationship-search-contract

## 节点定位

- `L1_capability`: `global-search-experience`
- `L2_journey`: `cross-domain-search-journey`
- `L3_scenario`: `social-relationship-search-contract`

## 背景与动机

产品上已经明确“朋友”应统一改成“社交关系”。这意味着搜索中的“人”不应该继续绑定到 chat contact 语义，而要收口到 user 域的社交关系与公开身份模型。

## 目标用户

- 需要查找社交关系对象并进入主页、发起互动或继续聊天的用户。

## 功能范围

- 冻结“社交关系”在搜索中的产品命名、对象边界与跳转语义。
- 明确其 metadata 真相源归属 `user/user_profile` 与 `user/follow_edge`。
- 定义搜索结果项展示的最小身份信息、关系态与跳转目标。

## Out of Scope

- follow/unfollow 写侧行为本身。
- 私密账号和密信隔离能力本身。
- chat 域联系人管理能力本身。

## 约束

- 搜索中的“人”统一命名为“社交关系”。
- “社交关系”不能再以 `SearchContacts` 作为长期产品真相源。
- 当前账号或登录子账号可见范围内的对象都允许进入结果。

## 对标输入与吸收结论

- 借鉴微信联系人搜索结果的清晰对象卡片与快捷操作，但领域归属改为 user 域社交关系对象。

## 角色分工

- `user`: 社交关系对象、公开身份、关系态真相源。
- `global-search-experience`: 结果组织、文案、入口与跳转。
- `chat`: 可作为后续快捷发起会话的消费方，但不是对象主定义方。

## 既有 Story 覆盖矩阵

| 历史节点 | 处理 |
|---|---|
| `contact-search-index` | 删除历史节点，归并到本 Scenario |
| `search-query-contract` | 删除历史节点，查询契约迁回 user 域与全局搜索 Journey |

## 数据生命周期合同

- 社交关系搜索结果为瞬时读模型。
- 历史搜索只记录 query 与 scope，不单独保存关系对象快照。

## 小趣 / 权限 / 分享边界

- 本 Scenario 不涉及问小趣逻辑。
- 本期不在账号内再做细粒度权限裁剪。

## 非功能目标

- 首批社交关系结果与其它结果分组一同在综合搜索首屏返回。
- 跳转到用户主页或关系详情的成功率 > 99%。

## 迁移、灰度与回滚要求

- 从特性树和 PRD 治理层彻底移除旧 chat 搜索节点。
- 如社交关系结果契约不稳定，整体回退到旧搜索实现，不保留旧节点并行。

## 验收重点

1. “社交关系”命名与对象边界冻结。
2. user 域成为搜索中“人”的真相源。
3. 旧 chat 搜索节点被彻底清理。
