import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
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
    String? description,
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
    String? description,
  }) async {
    submitted.add(<String, dynamic>{
      'targetId': targetId,
      'targetType': targetType,
      'reason': reason,
      if (description != null && description.isNotEmpty) 'description': description,
    });
  }
}

/// Remote 实现：调用云侧 API。
class RemoteReportRepository extends ReportRepository {
  RemoteReportRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<void> createReport({
    required String targetId,
    required String targetType,
    required String reason,
    String? description,
  }) async {
    final uri = _uri(ContentApiMetadata.createReportPath);
    final body = <String, dynamic>{
      'targetId': targetId,
      'targetType': targetType,
      'reason': reason,
      if (description != null && description.isNotEmpty) 'description': description,
    };
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.createReport),
      body: body,
    );
  }
}
