import 'package:quwoquan_app/application/content/post/author_impact_query.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_evidence_page.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// Content/Post 作者影响力的 production Remote adapter。
final class RemoteAuthorImpactQuery implements AuthorImpactQuery {
  factory RemoteAuthorImpactQuery({
    required CloudHttpClient httpClient,
    String? baseUrl,
  }) {
    return RemoteAuthorImpactQuery._(
      httpClient,
      (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
    );
  }

  const RemoteAuthorImpactQuery._(this._httpClient, this._baseUrl);

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) =>
      Uri.parse('$_baseUrl$path').replace(queryParameters: queryParameters);

  Future<Map<String, dynamic>> _getObject(
    String path,
    String clientPageId, {
    Map<String, String>? queryParameters,
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(path, queryParameters: queryParameters),
      headers: CloudRequestHeaders.forPage(clientPageId),
    );
    final root = CloudResponseDecoder.asObject(decoded, context: clientPageId);
    final data = root['data'];
    if (data is Map<String, dynamic>) {
      return data;
    }
    if (data is Map) {
      return Map<String, dynamic>.from(data);
    }
    return root;
  }

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String subAccountId) async {
    final data = await _getObject(
      ContentApiMetadata.getAuthorImpactPath(subAccountId: subAccountId),
      ContentRequestPageIds.getAuthorImpact,
      queryParameters: const <String, String>{'limit': '12'},
    );
    return AuthorImpactSummary.fromMap(data);
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String subAccountId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final data = await _getObject(
      ContentApiMetadata.listAuthorImpactEvidencePath(
        subAccountId: subAccountId,
      ),
      ContentRequestPageIds.listAuthorImpactEvidence,
      queryParameters: <String, String>{
        'impactId': impactId,
        'limit': '$limit',
        if (evidenceSnapshotId.trim().isNotEmpty)
          'evidenceSnapshotId': evidenceSnapshotId.trim(),
        if (cursor.trim().isNotEmpty) 'cursor': cursor.trim(),
      },
    );
    return AuthorImpactEvidencePage.fromMap(data);
  }
}
