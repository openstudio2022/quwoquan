import 'package:quwoquan_app/service/product_ops_service/product_ops/app_release/application/app_release_recovery_reader.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AppReleaseRecoveryInvocationContextFactory =
    CloudOperationInvocationContext Function();

final class RemoteAppReleaseRecoveryReader
    implements AppReleaseRecoveryReader {
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
    return AppReleaseRecoveryFacts(
      latestVersion: response.latestVersion.trim(),
      latestBuild: latestBuild,
      updateUrl: response.updateUrl?.trim(),
      recoveryUrl: response.recoveryUrl.trim(),
    );
  }
}
