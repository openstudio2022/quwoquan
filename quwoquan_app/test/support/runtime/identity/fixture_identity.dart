/// 测试树的当前用户 variant 身份单一真相源。
///
/// user_account 的 profile builder 与 account_session 的 auth facets 都要
/// 引用同一个「当前登录用户」fixture 身份;对象 support 之间不允许互相
/// import,所以该身份上收到 runtime harness,两侧共同消费。
/// persona 与 user 是两个对象:当前 fixture 尚未拆分(同值),未来拆分时
/// 只改这里,消费方自动跟上,不会出现第二份硬编码。
const String fixtureCurrentUserVariantUserId = 'fixture_user_current';
const String fixtureCurrentUserVariantPersonaId = fixtureCurrentUserVariantUserId;
