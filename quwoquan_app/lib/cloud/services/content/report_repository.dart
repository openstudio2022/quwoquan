import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// 举报 Repository（三层模式：Abstract → Mock → Remote）
///
/// 对应云侧路由（contracts/metadata/content/report/service.yaml）：
///   POST /v1/content/reports
abstract class ReportRepository {
  Future<void> createReport({
    required String targetId,
    required String targetType,
    required String reason,
    String? note,
  });
}

/// Mock 实现：本地记录，不发 HTTP 请求。
class MockReportRepository extends ReportRepository {
  final List<Map<String, dynamic>> submitted = <Map<String, dynamic>>[];

  @override
  Future<void> createReport({
    required String targetId,
    required String targetType,
    required String reason,
    String? note,
  }) async {
    submitted.add(<String, dynamic>{
      'targetId': targetId,
      'targetType': targetType,
      'reason': reason,
      'note': ?note,
    });
  }
}

/// Remote 实现：调用云侧 API。
class RemoteReportRepository extends ReportRepository {
  RemoteReportRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  })  : _httpClient = httpClient ?? CloudHttpClient(client: client ?? http.Client()),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<void> createReport({
    required String targetId,
    required String targetType,
    required String reason,
    String? note,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/reports');
    final body = <String, dynamic>{
      'targetId': targetId,
      'targetType': targetType,
      'reason': reason,
      if (note != null && note.isNotEmpty) 'note': note,
    };
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.report.create'),
      body: body,
    );
  }
}
