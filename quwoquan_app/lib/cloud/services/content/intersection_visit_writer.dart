import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// IntersectionVisitState 对象的 typed 写面
/// （contracts/metadata/content/intersection_visit_state/service.yaml）。
///
/// 推进「我的交集」已读水位并清零未读红点；[dimension] 为空推进全部维度。
/// 服务端水位以 $max 单调合并，任意重放自然收敛（无需 Idempotency-Key）。
abstract class IntersectionVisitWriter {
  Future<void> markIntersectionsVisited({String? dimension});
}

class RemoteIntersectionVisitWriter implements IntersectionVisitWriter {
  factory RemoteIntersectionVisitWriter({
    required CloudHttpClient httpClient,
    String? baseUrl,
  }) {
    return RemoteIntersectionVisitWriter._(
      httpClient,
      (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
    );
  }

  RemoteIntersectionVisitWriter._(this._httpClient, this._baseUrl);

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<void> markIntersectionsVisited({String? dimension}) async {
    await _httpClient.postJson(
      Uri.parse('$_baseUrl${ContentApiMetadata.markIntersectionsVisitedPath}'),
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.markIntersectionsVisited,
      ),
      body: <String, dynamic>{'dimension': (dimension ?? '').trim()},
    );
  }
}
