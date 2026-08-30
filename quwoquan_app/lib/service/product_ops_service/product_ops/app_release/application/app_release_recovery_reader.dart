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

enum AppReleaseUpdateState { none, available, required }

enum AppReleaseRecoveryPlatform { android, ios, web }

enum AppReleaseRecoveryChannel { nativeUpdate, webOnly }

final class AppReleaseRecoveryFacts {
  const AppReleaseRecoveryFacts({
    required this.platform,
    required this.latestVersion,
    required this.latestBuild,
    required this.minimumSupportedVersion,
    required this.minimumSupportedBuild,
    required this.updateState,
    required this.updateChannel,
    required this.updateUrl,
    required this.recoveryUrl,
  });

  final AppReleaseRecoveryPlatform platform;
  final String latestVersion;
  final int latestBuild;
  final String minimumSupportedVersion;
  final int minimumSupportedBuild;
  final AppReleaseUpdateState updateState;
  final AppReleaseRecoveryChannel updateChannel;
  final String? updateUrl;
  final String recoveryUrl;
}

abstract interface class AppReleaseRecoveryReader {
  Future<AppReleaseRecoveryFacts> read(AppReleaseRecoveryQuery query);
}
