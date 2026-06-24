class LocalDevHttpsTrust {
  LocalDevHttpsTrust._();

  static Future<void> installForCurrentRuntime() async {}

  static bool shouldInstallForRuntime({
    required bool isReleaseMode,
    required bool isAndroid,
    required String appRuntimeEnv,
    required Iterable<String> runtimeBases,
  }) {
    return false;
  }
}
