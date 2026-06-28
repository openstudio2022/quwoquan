/// alpha / mock 环境下「当前用户」的标准身份。
///
/// T3 切流后指向 creator pool `currentUserVariant` 槽位；`fixture_user_current`
/// 保留为 legacy alias，经 [PrefabUserResolver] 双读解析。
///
/// 设计约定：
/// - mock 不区分 owner 与主分身（user 主体即主分身），故 owner 与 subAccount
///   归一为同一身份。
/// - 这是 mock 链路里「当前登录用户」的唯一真相源；auth 登录结果、会话刷新、
///   资料编辑回写都必须复用本常量，禁止再散落 `mock_sub_id` / `mock_owner_id`。
import 'package:quwoquan_app/cloud/runtime/prefab_user_resolver.dart';

/// 见 [PrefabUserResolver.currentUserVariantUserId]：mock 当前用户 owner 标识。
String get kMockCurrentOwnerId => PrefabUserResolver.currentUserVariantUserId;

/// 见 [PrefabUserResolver.currentUserVariantSubAccountId]：mock 当前用户主分身标识。
String get kMockCurrentSubAccountId => PrefabUserResolver.currentUserVariantSubAccountId;
