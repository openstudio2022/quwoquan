import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';

/// 启动恢复从 effective launch manifest 获得的不可变最小运行时绑定。
///
/// 恢复路径发生在普通 runtime config 可能尚未装载或已经损坏时，因此这里不读取
/// compile-time defines，也不接受未绑定候选身份的任意 URL。
final class RecoveryRuntimeBinding {
  factory RecoveryRuntimeBinding.fromLaunchManifest({
    required String environment,
    required String recoveryBaseUrl,
    required String runtimeConfigDigest,
    required String effectiveLaunchManifestDigest,
  }) {
    final normalizedEnvironment = environment.trim();
    final cloudEnvironment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == normalizedEnvironment,
      orElse: () => throw const FormatException(
        'invalid recovery runtime environment',
      ),
    );
    final recoveryOrigin = Uri.tryParse(recoveryBaseUrl.trim());
    if (recoveryOrigin == null ||
        recoveryOrigin.scheme.toLowerCase() != 'https' ||
        recoveryOrigin.host.isEmpty ||
        recoveryOrigin.userInfo.isNotEmpty ||
        recoveryOrigin.hasQuery ||
        recoveryOrigin.hasFragment ||
        (recoveryOrigin.path.isNotEmpty && recoveryOrigin.path != '/')) {
      throw const FormatException('invalid recovery runtime origin');
    }
    final normalizedRuntimeDigest = runtimeConfigDigest.trim();
    final normalizedManifestDigest = effectiveLaunchManifestDigest.trim();
    if (!_sha256Identity.hasMatch(normalizedRuntimeDigest) ||
        !_sha256Identity.hasMatch(normalizedManifestDigest)) {
      throw const FormatException('invalid recovery runtime identity');
    }
    return RecoveryRuntimeBinding._(
      environment: cloudEnvironment,
      recoveryOrigin: recoveryOrigin.replace(
        path: '',
        query: null,
        fragment: null,
      ),
      runtimeConfigDigest: normalizedRuntimeDigest,
      effectiveLaunchManifestDigest: normalizedManifestDigest,
    );
  }

  const RecoveryRuntimeBinding._({
    required this.environment,
    required this.recoveryOrigin,
    required this.runtimeConfigDigest,
    required this.effectiveLaunchManifestDigest,
  });

  static final RegExp _sha256Identity = RegExp(r'^sha256:[0-9a-f]{64}$');

  final CloudEnvironment environment;
  final Uri recoveryOrigin;
  final String runtimeConfigDigest;
  final String effectiveLaunchManifestDigest;

  String get identity =>
      '${environment.name}|$recoveryOrigin|$runtimeConfigDigest|'
      '$effectiveLaunchManifestDigest';
}
