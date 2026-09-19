import 'package:quwoquan_cloud_contracts/generated/values/user/account/authentication_challenge.values.dart';

/// 非认证本地流程；只能在已验证 isolated 绑定且三存储隔离完成后装配。
/// 失败抛出同源生成的 SyntheticLoginFailure，不返回默认成功或发起 SMS。
abstract interface class SyntheticChallengePort {
  Future<SyntheticChallengeView> begin(BeginSyntheticChallenge command);
}
