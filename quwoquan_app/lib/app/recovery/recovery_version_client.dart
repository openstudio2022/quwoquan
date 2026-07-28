import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';

class RecoveryVersionResult {
  const RecoveryVersionResult({
    required this.latestVersion,
    required this.latestBuild,
    required this.updateUrl,
    required this.recoveryUrl,
  });

  final String latestVersion;
  final int latestBuild;
  final String updateUrl;
  final String recoveryUrl;
}

final class RecoveryVersionClient {
  RecoveryVersionClient({http.Client? client})
    : _client = client ?? http.Client();

  final http.Client _client;

  Future<RecoveryVersionResult> fetch({
    required String baseUrl,
    required String platform,
    required String appVersion,
    required int buildNumber,
  }) async {
    final origin = Uri.parse(baseUrl.trim());
    if (origin.scheme != 'https' ||
        origin.host.isEmpty ||
        origin.userInfo.isNotEmpty) {
      throw const FormatException('invalid recovery origin');
    }
    final uri = origin.replace(
      path: OpsApiMetadata.getAppRecoveryVersionPath,
      queryParameters: <String, String>{
        'platform': platform,
        'appVersion': appVersion,
        'buildNumber': '$buildNumber',
      },
    );
    final response = await _client.get(
      uri,
      headers: const <String, String>{'Accept': 'application/json'},
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('version service unavailable');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic> || decoded.length != 4) {
      throw const FormatException('invalid recovery version response');
    }
    final latestBuild = int.tryParse(decoded['latestBuild']?.toString() ?? '');
    final result = RecoveryVersionResult(
      latestVersion: decoded['latestVersion']?.toString().trim() ?? '',
      latestBuild: latestBuild ?? 0,
      updateUrl: decoded['updateUrl']?.toString().trim() ?? '',
      recoveryUrl: decoded['recoveryUrl']?.toString().trim() ?? '',
    );
    if (result.latestVersion.isEmpty || result.latestBuild <= 0) {
      throw const FormatException('invalid recovery release values');
    }
    return result;
  }
}
