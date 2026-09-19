import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';

/// 合成确认不等于六位 OTP；不能转换为 Remote AuthSessionGrant。
/// 失败抛出 SyntheticLoginFailure；持久化未完成不得返回成功结果。
abstract interface class SyntheticSessionPort {
  Future<SyntheticSessionResult> complete(CompleteSyntheticChallenge command);
}
