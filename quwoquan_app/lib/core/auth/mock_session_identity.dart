/// alpha / mock 环境下「当前用户」的标准身份。
///
/// 统一指向 contract seed `fixture_user_current`（`user_profile_core`），
/// 让我的主页 / 资料编辑在 mock 下读到真实种子档案，而不是 `mock_sub_id` 占位。
///
/// 设计约定：
/// - mock 不区分 owner 与主分身（user 主体即主分身），故 owner 与 subAccount
///   归一为同一身份。
/// - 这是 mock 链路里「当前登录用户」的唯一真相源；auth 登录结果、会话刷新、
///   资料编辑回写都必须复用本常量，禁止再散落 `mock_sub_id` / `mock_owner_id`。
const String kMockCurrentOwnerId = 'fixture_user_current';

/// 见 [kMockCurrentOwnerId]：mock 当前用户的主分身（subAccount）标识。
const String kMockCurrentSubAccountId = 'fixture_user_current';
