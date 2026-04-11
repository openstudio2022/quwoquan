# 用户域 API / 类型盘点（dynamic / Map 边界）

> 与「用户域去 dynamic 整改」计划对齐：标明每条能力的返回形状、OpenAPI 覆盖与目标强类型。  
> 更新：2026-04-11（auth / invite / greeting / user_profile 远程 GET/POST 主路径已 `asObject`；`UserRepository` 使用 `getJsonObject` / `getJsonItemList` / `postJsonObject` / `patchJsonObject`，业务文件无 `Object?` 解码形参。）

## 1. 原则边界

| 层级 | 说明 |
|------|------|
| HTTP | `CloudHttpClient.getJson` / `postJson` 等仍返回 `Future<dynamic>`，为全仓基座；对象/列表根已在基座侧增加 `getJsonObject`、`getJsonItemList`、`postJsonObject`、`patchJsonObject`（内部 `getJson` + `asObject`）。 |
| 解码点 | `json.decode` / `getJson` 之后 **第一步** `CloudResponseDecoder.asObject`（接受任意 `Map`）/ `mapList` / `mapListFirstNonEmpty`，再 `*WireDto.fromMap`。 |
| 业务出口 | `UserProfileRepository` / `UserRepository` 对外保持 `ProfileSubjectViewData` 等 View；内部用 `*WireDto`（metadata `client_projection`）。 |
| 生成物 | 独立 wire 类构造器 **非 const**（避免 `DateTime` / 集合默认值非法）；调用方使用 `fromMap` / `copyWith`。 |

## 2. UserProfileRepository 方法 → 目标类型

| 方法 | 当前主路径 | OpenAPI / service | Wire DTO（codegen） |
|------|------------|-------------------|---------------------|
| `getUserProfile` / `getProfileSubject` | `ProfileSubjectWireDto` → `fromProfileSubjectWire` | profile 路由 | `ProfileSubjectWireDto` |
| `getUserStats` | `UserProfileStatsViewData.fromProfile` | 无独立 stats | **N/A** |
| `listFollowing` / `listFollowers` | `ProfileSocialRelationRowWireDto` → View | follow 列表 | `ProfileSocialRelationRowWireDto` |
| `listUserLikes` | `ProfileUserLikeRowWireDto` → View | user_profile | `ProfileUserLikeRowWireDto` |
| `listUserInteractionReceived` / `Sent` | `_decodeItems` → `mapList` + ActivityWire | content/user | `ProfileInteractionActivityWireDto` |
| `getRelationship` | `_normalizeRelationship` → `RelationshipNormalizedWireDto` | relationship | `RelationshipNormalizedWireDto` |
| `searchSocialRelations` | `SocialRelationSearchItemWireDto` + 行 Map capability 回退 | user openapi + metadata | `SocialRelationSearchItemWireDto` |
| `listRecentSearches` / `upsertRecentSearch` | `RecentSearchEntryWireDto` | user | `RecentSearchEntryWireDto` |
| `listPersonas` / `createPersona` | `mapList` + `asObject` + `PersonaDto` | openapi personas | `Persona`（已有 DTO） |
| `listUserPosts` / `listUserWorks` / `listUserLifeItems` / `listUserCircles` | `asObject` + `mapList` | 各域 openapi | 内容/Circle 侧 DTO |

## 3. UserRepository 与其它用户域 Repository

| 区域 | 路径 | Wire / 解码 |
|------|------|----------------|
| `listSubAccounts` | `CloudHttpClient.getJsonItemList`（根数组或对象内 `items` / `subAccounts` / `personas`） | `PersonaManagementItemWireDto` |
| `getPersonaManagementSummary` | `PersonaManagementSummaryWireDto.fromMap` → `fromPersonaManagementSummaryWire` | `PersonaManagementSummaryWireDto`（items 多键、quota/activeContext 嵌套 Map） |
| `getActivePersonaContext` | `ActivePersonaContextWireDto` | 已有 |
| `getSubAccountLifecycleGuard` | `PersonaLifecycleGuardWireDto` | 已有 |
| `RelationshipCapabilityRepository` | `CloudResponseDecoder.asObject` + `RelationshipCapabilityWireDto` → `fromRelationshipCapabilityWire` | `RelationshipCapabilityWireDto` |
| `RemoteAppearanceSettingsRepository` | `AppearanceSettingsWireDto` → `AppearanceSettingsSnapshot.fromAppearanceSettingsWire` | `AppearanceSettingsWireDto` |
| `RemoteCallSettingsRepository` | `CallSettingsWireDto` → `CallSettingsDto.fromCallSettingsWire` | `CallSettingsWireDto` |
| `RemoteKeywordBlockRepository` | 读隐私接口：`PrivacySettingsWireDto`（`blockedKeywords`） | `PrivacySettingsWireDto` |

## 4. OpenAPI（user 包）

- 已补充：`/v1/user/settings/calls`、`RelationshipCapability`、`PersonaManagementSummary`、`PrivacySettings.blockedKeywords` 等（见 `quwoquan_service/contracts/metadata/user/openapi.yaml`）。

## 5. 与 metadata 唯一源关系

- 投影路径：`quwoquan_service/contracts/metadata/user/**/projections/*.yaml`（`client_projection.base_class: ""`）。  
- 生成：`make -C quwoquan_service codegen-app` → `quwoquan_app/lib/cloud/runtime/generated/user/*_wire_dto.g.dart`。  
- `List<Map>` 多键别名：codegen 生成 `_firstNonEmptyMapList`；运行时列表多键回退见 `CloudResponseDecoder.mapListFirstNonEmpty`。

## 6. 测试

- 契约：`quwoquan_app/test/cloud/user/contract/user_profile_wire_dto_contract_test.dart`（含 summary / capability / appearance / call / privacy wire）。  
- 解码：`test/cloud/runtime/codec/cloud_response_decoder_test.dart`（`asObject` 泛型 Map、`mapListFirstNonEmpty`）。  
- Mock：`MockUserProfileRepository` 等仍以 JSON 字符串解码 → `WireDto.fromMap` → View，与 Remote 同链。
