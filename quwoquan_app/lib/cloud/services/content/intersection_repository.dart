import 'package:quwoquan_app/cloud/runtime/cloud_api_query_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_inbox_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';

/// 交集读面。production 组合根只装配 [RemoteIntersectionRepository]；
/// alpha/test adapter 位于独立 runner，不进入生产可达图。
abstract class IntersectionRepository {
  Future<IntersectionInboxSummary> getMyIntersectionSummary();

  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  });

  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  });
}

class RemoteIntersectionRepository implements IntersectionRepository {
  factory RemoteIntersectionRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
    String? currentUserId,
  }) {
    // viewer 身份只来自显式注入（production provider 传登录态 currentUserIdProvider；
    // 测试传 fixture id）。禁止编译期 dart-define 回退——未登录请求由服务端结构化
    // 401 fail-fast，不得以构建期身份静默伪装 viewer（R-IX08 收口）。
    return RemoteIntersectionRepository._(
      httpClient ?? CloudHttpClient(),
      (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
      (currentUserId ?? '').trim(),
    );
  }

  RemoteIntersectionRepository._(
    this._httpClient,
    this._baseUrl,
    this._currentUserId,
  );

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  final String _currentUserId;

  Uri _uri(String path, [Map<String, String>? query]) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: query == null || query.isEmpty ? null : query);
  }

  Map<String, String> _headers(String pageId) {
    return CloudRequestHeaders.withOwnerPersonaContext(
      CloudRequestHeaders.forPage(pageId),
      ownerUserId: _currentUserId,
      personaId: _currentUserId,
    );
  }

  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.getMyIntersectionSummaryPath),
      headers: _headers(ContentRequestPageIds.getMyIntersectionSummary),
    );
    return IntersectionInboxSummary.fromMap(
      CloudResponseDecoder.asObject(
        decoded,
        context: ContentRequestPageIds.getMyIntersectionSummary,
      ),
    );
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = CloudApiQueryDefaults.intersectionListLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if ((dimension ?? '').trim().isNotEmpty) {
      query['dimension'] = dimension!.trim();
    }
    if ((filter ?? '').trim().isNotEmpty) {
      query['filter'] = filter!.trim();
    }
    if ((sourceRef ?? '').trim().isNotEmpty) {
      query['sourceRef'] = sourceRef!.trim();
    }
    if ((timeBucket ?? '').trim().isNotEmpty) {
      query['timeBucket'] = timeBucket!.trim();
    }
    if ((cursor ?? '').trim().isNotEmpty) {
      query['cursor'] = cursor!.trim();
    }
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.listMyIntersectionsPath, query),
      headers: _headers(ContentRequestPageIds.listMyIntersections),
    );
    final object = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.listMyIntersections,
    );
    return filterDefaultInboxLifecycle(
      CloudResponseDecoder.mapList(
        object,
        'items',
      ).map(IntersectionReason.fromMap).toList(growable: false),
    );
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = CloudApiQueryDefaults.objectIntersectionsLimit,
  }) async {
    final decoded = await _httpClient.getJson(
      _uri(ContentApiMetadata.getObjectIntersectionsPath, <String, String>{
        'objectId': objectId,
        'objectType': objectType,
        'limit': '$limit',
      }),
      headers: _headers(ContentRequestPageIds.getObjectIntersections),
    );
    final object = CloudResponseDecoder.asObject(
      decoded,
      context: ContentRequestPageIds.getObjectIntersections,
    );
    return CloudResponseDecoder.mapList(
      object,
      'items',
    ).map(IntersectionReason.fromMap).toList(growable: false);
  }
}
