final class AppReleaseRecoveryQuery {
  const AppReleaseRecoveryQuery({
    required this.platform,
    required this.appVersion,
    required this.buildNumber,
  });

  final String platform;
  final String appVersion;
  final int buildNumber;
}

final class AppReleaseRecoveryFacts {
  const AppReleaseRecoveryFacts({
    required this.latestVersion,
    required this.latestBuild,
    required this.updateUrl,
    required this.recoveryUrl,
  });

  final String latestVersion;
  final int latestBuild;
  final String? updateUrl;
  final String recoveryUrl;
}

abstract interface class AppReleaseRecoveryReader {
  Future<AppReleaseRecoveryFacts> read(AppReleaseRecoveryQuery query);
}
