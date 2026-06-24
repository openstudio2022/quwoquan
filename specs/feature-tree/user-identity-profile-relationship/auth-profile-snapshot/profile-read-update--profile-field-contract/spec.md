# L3 Story：profile-read-update--profile-field-contract

## Spec Entry
- 阶段：`/design` → `/dev`，本轮冻结并实现编辑资料地区字段端云契约。
- AppRoot Journey/Scenario：我的主页 → 编辑资料 → 地区选择 → 保存 → 我的主页/编辑页回显。
- L1_domain_service：`user-identity-profile-relationship`。
- L2_business_capability：`auth-profile-snapshot`。
- L3_story：`profile-read-update--profile-field-contract`。
- 验收意图：`UAT / SIT / GWT / contract`。
- 测试证据：`local_contract / api_integration / user_acceptance`。

## 用户价值
- 用户在编辑资料时选择地区，看到完整的中国省级和所选省份 direct children，不再因为 App 或 user-service 手写短表缺少二级行政区。
- 客户端保存稳定 `regionTagRef`，展示文案由服务端从标签链路派生，避免任意字符串污染用户画像、推荐和运营分析。

## 范围
- V1 只支持中国行政区两级选择：一级为省级行政区，二级为该省直接子节点；普通省为地级市/州/地区/省直辖县级单位，直辖市为区县。
- `quwoquan_data/publish/tags` 是行政区标签源头真相；服务端 Mongo `tag_nodes` 是线上 serving projection；App 不内置地区配置，user-service 不维护行政区 catalog。
- tag-service 新增公共只读层级接口 `GET /v1/tag/children?parentTagRef=...&limit=500`，与地图/POI 同属公共能力，但语义归属标签系统。

## Out Of Scope
- 普通省份第三层区县选择不在本轮；若后续要精确到 `深圳市/南山区`，新增三层 UI 与独立验收。
- 境外行政区沿用同一 children 接口后续扩展，不在本轮填充完整数据。
- 本轮不把标签树打包为 App 配置或 user-service 镜像配置。

## 契约
- Tag API：`ListTagChildren` 返回 `TagChildView[]`，字段为 `tagRef / label / displayLabel / labelEn / parentTagRef / depth / hasChildren / releaseId / lifecycleStatus`。
- User API：`PATCH /v1/user/profile` 使用 `regionTagRef`，不接受客户端提交任意非空 `region`；`ProfileEditSnapshotWire` 返回 `region + regionTagRef`。
- Error：无效、不在 `Topic/地理/行政区/中国/` 下或不存在的行政区引用统一使用 `USER.PROFILE.invalid_region`。
- Storage：`TagNode` serving projection 包含 `parentTagRef / displayLabel / releaseId / lifecycleStatus`，索引为 `{ parentTagRef, lifecycleStatus, tagRef }`。

## 数据更新路径
- 数据工程通过 taxonomy CLI/脚本生成并校验 `publish/tags/Topic/地理/行政区/中国/**/_definition.json`。
- 发布后由 `services/tag-service/cmd/import` 幂等导入 Mongo `tag_nodes`，导入器派生 direct parent、短展示名、releaseId 与 active lifecycle。
- tag-service 可做只读缓存，但缓存只能从 Mongo warm；不得从 App 本地文件、user-service 配置或镜像配置维护第二份行政区树。

## 三层测试
- local_contract：
  - `quwoquan_data/tests/local_contract/publish/test_admin_region_tags__local_contract_test.py` 校验中国 34 省级、广东 21 direct children、北京 16 区县。
  - tag-service contract 测 `ListTagChildren` direct children、`hasChildren`、未知 parent 404。
  - App `TagChild.fromJson` 和 Mock `TagRepository.listChildren` 锁定字段一致性。
  - user-service contract 测有效 `regionTagRef` 更新、非行政区/展示文案写入返回 `USER.PROFILE.invalid_region`。
- api_integration：
  - tag-service 真实 Mongo seed 后调用 `/v1/tag/children` 验证广东/北京样例。
  - user-service PATCH profile 返回 `region + regionTagRef`，错误码链路保持结构化。
- user_acceptance：
  - 我的主页 → 编辑资料 → 地区 → 广东 → 深圳 → 保存，payload 包含 `regionTagRef` 且不包含 `regionCode`。
