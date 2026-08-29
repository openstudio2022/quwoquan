import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/application/app_release_recovery_reader.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AppReleaseRecoveryInvocationContextFactory =
    CloudOperationInvocationContext Function();

final class RemoteAppReleaseRecoveryReader implements AppReleaseRecoveryReader {
  const RemoteAppReleaseRecoveryReader({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AppReleaseRecoveryInvocationContextFactory invocationContext;

  @override
  Future<AppReleaseRecoveryFacts> read(AppReleaseRecoveryQuery query) async {
    final response = await client.opsAppReleaseGetAppRecoveryVersion(
      ops_contracts.GetAppRecoveryVersionQuery(
        platform: query.platform,
        appVersion: query.appVersion,
        buildNumber: query.buildNumber,
      ),
      context: invocationContext(),
    );
    final latestBuild = int.tryParse(response.latestBuild.trim());
    if (latestBuild == null || latestBuild <= 0) {
      throw const FormatException('invalid recovery release build');
    }
    final minimumSupportedBuild = int.tryParse(
      response.minimumSupportedBuild.trim(),
    );
    if (minimumSupportedBuild == null ||
        minimumSupportedBuild <= 0 ||
        minimumSupportedBuild > latestBuild) {
      throw const FormatException('invalid minimum supported release build');
    }
    final platformWire = response.platform.trim();
    final identity = _recoveryIdentityFromWire(platformWire);
    if (platformWire != query.platform.trim().toLowerCase()) {
      throw const FormatException('recovery release platform mismatch');
    }
    final updateState = switch (response.updateState) {
      ops_contracts.AppReleaseUpdateState.none => AppReleaseUpdateState.none,
      ops_contracts.AppReleaseUpdateState.available =>
        AppReleaseUpdateState.available,
      ops_contracts.AppReleaseUpdateState.required =>
        AppReleaseUpdateState.required,
    };
    final expectedUpdateState = switch (query.buildNumber) {
      final build when build < minimumSupportedBuild =>
        AppReleaseUpdateState.required,
      final build when build < latestBuild => AppReleaseUpdateState.available,
      _ => AppReleaseUpdateState.none,
    };
    if (updateState != expectedUpdateState) {
      throw const FormatException('recovery release update state mismatch');
    }
    final updateUrl = response.updateUrl?.trim();
    if (updateUrl != null && updateUrl.isEmpty) {
      throw const FormatException('invalid recovery release update url');
    }
    final hasCanonicalUpdateChannel = switch (identity.updateChannel) {
      AppReleaseRecoveryChannel.nativeUpdate => updateUrl != null,
      AppReleaseRecoveryChannel.webOnly => updateUrl == null,
    };
    if (!hasCanonicalUpdateChannel) {
      throw const FormatException('recovery release update channel mismatch');
    }
    return AppReleaseRecoveryFacts(
      platform: identity.platform,
      latestVersion: response.latestVersion.trim(),
      latestBuild: latestBuild,
      minimumSupportedVersion: response.minimumSupportedVersion.trim(),
      minimumSupportedBuild: minimumSupportedBuild,
      updateState: updateState,
      updateChannel: identity.updateChannel,
      updateUrl: updateUrl,
      recoveryUrl: response.recoveryUrl.trim(),
    );
  }
}

({AppReleaseRecoveryPlatform platform, AppReleaseRecoveryChannel updateChannel})
_recoveryIdentityFromWire(String platform) => switch (platform) {
  'android' => (
    platform: AppReleaseRecoveryPlatform.android,
    updateChannel: AppReleaseRecoveryChannel.nativeUpdate,
  ),
  'ios' => (
    platform: AppReleaseRecoveryPlatform.ios,
    updateChannel: AppReleaseRecoveryChannel.webOnly,
  ),
  'web' => (
    platform: AppReleaseRecoveryPlatform.web,
    updateChannel: AppReleaseRecoveryChannel.nativeUpdate,
  ),
  _ => throw const FormatException('invalid recovery release platform'),
};
