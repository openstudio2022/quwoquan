import 'dart:convert';

import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/tag/tag_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/tag/tag_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

// Facet 契约与 DTO 唯一真相源在 pure contracts；此处透传导出以稳定既有 import。
export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        TagApiDefaults,
        TagTaxonomyRefs,
        TagCatalogQuery,
        TagGraphQuery,
        SharedTagView,
        TagResolve,
        TagChild,
        TagDimension,
        TagSuggestion,
        TagValidationResult,
        TagRefSuggestion,
        TagSearchResult,
        RelatedTag,
        TagObjectMatch,
        TagCooccurrence,
        TagInvertedResult,
        RelatedObject;

/// tag 域共享 HTTP 传输基座：path / pageId 全部来自 codegen 真相源
/// （TagApiMetadata / TagRequestPageIds），不得硬编码路径（军规 R06/R09）。
/// 解码统一经 [CloudResponseDecoder]，直出强类型 DTO（StrictTyping，
/// 门禁见 verify_cloud_tag_strict_typing.py）。
abstract base class _TagRemoteTransport {
  _TagRemoteTransport({CloudHttpClient? httpClient})
    : _httpClient = httpClient ?? CloudHttpClient();

  final CloudHttpClient _httpClient;

  Uri _uri(String path, [Map<String, String>? params]) => Uri.parse(
    '${CloudRuntimeConfig.gatewayBaseUrl}$path',
  ).replace(queryParameters: params);

  Never _fail(int statusCode, String body, String path) {
    throw CloudErrorMapper.fromStatusCode(
      statusCode,
      body: body,
      requestPath: path,
    );
  }

  List<T> _asEntityList<T>(
    Object? decoded,
    T Function(CloudJsonMap) fromJson,
    String context,
  ) {
    if (decoded is! List) {
      throw CloudErrorMapper.invalidResponse(
        message: 'Tag API expected list response at $context',
        requestPath: context,
        functionModule: 'tag_repository_remote',
      );
    }
    final out = <T>[];
    for (final e in decoded) {
      if (e is Map<String, dynamic>) {
        out.add(fromJson(e));
      } else if (e is Map) {
        out.add(fromJson(Map<String, dynamic>.from(e)));
      }
    }
    return out;
  }

  Future<List<T>> _getList<T>(
    String path,
    String pageId,
    T Function(CloudJsonMap) fromJson, [
    Map<String, String>? params,
  ]) async {
    final resp = await _httpClient.get(
      _uri(path, params),
      headers: CloudRequestHeaders.forPage(pageId),
    );
    if (resp.statusCode != 200) _fail(resp.statusCode, resp.body, path);
    return _asEntityList(json.decode(resp.body), fromJson, path);
  }

  Future<T> _getObject<T>(
    String path,
    String pageId,
    T Function(CloudJsonMap) fromJson, [
    Map<String, String>? params,
  ]) async {
    final resp = await _httpClient.get(
      _uri(path, params),
      headers: CloudRequestHeaders.forPage(pageId),
    );
    if (resp.statusCode != 200) _fail(resp.statusCode, resp.body, path);
    return fromJson(
      CloudResponseDecoder.asObject(json.decode(resp.body), context: path),
    );
  }

  Future<List<T>> _postList<T>(
    String path,
    String pageId,
    CloudJsonMap body,
    T Function(CloudJsonMap) fromJson,
  ) async {
    final resp = await _httpClient.post(
      _uri(path),
      headers: {
        ...CloudRequestHeaders.forPage(pageId),
        'Content-Type': 'application/json',
      },
      body: json.encode(body),
    );
    if (resp.statusCode != 200) _fail(resp.statusCode, resp.body, path);
    return _asEntityList(json.decode(resp.body), fromJson, path);
  }

  Future<T> _postObject<T>(
    String path,
    String pageId,
    CloudJsonMap body,
    T Function(CloudJsonMap) fromJson,
  ) async {
    final resp = await _httpClient.post(
      _uri(path),
      headers: {
        ...CloudRequestHeaders.forPage(pageId),
        'Content-Type': 'application/json',
      },
      body: json.encode(body),
    );
    if (resp.statusCode != 200) _fail(resp.statusCode, resp.body, path);
    return fromJson(
      CloudResponseDecoder.asObject(json.decode(resp.body), context: path),
    );
  }
}

/// TagCatalogQuery 的 production Remote adapter。
final class RemoteTagCatalogQuery extends _TagRemoteTransport
    implements TagCatalogQuery {
  RemoteTagCatalogQuery({super.httpClient});

  @override
  Future<List<TagChild>> listChildren(
    String parentTagRef, {
    int limit = TagApiDefaults.childrenLimit,
  }) {
    return _getList(
      TagApiMetadata.listTagChildrenPath,
      TagRequestPageIds.listTagChildren,
      TagChild.fromJson,
      <String, String>{'parentTagRef': parentTagRef, 'limit': '$limit'},
    );
  }

  @override
  Future<TagResolve> resolveTag(String tagRef) => _getObject(
    TagApiMetadata.resolveTagPath,
    TagRequestPageIds.resolveTag,
    TagResolve.fromJson,
    <String, String>{'tagRef': tagRef},
  );

  @override
  Future<List<TagDimension>> listDimensions() => _getList(
    TagApiMetadata.listDimensionsPath,
    TagRequestPageIds.listDimensions,
    TagDimension.fromJson,
  );

  @override
  Future<List<TagSuggestion>> suggest(
    String query, {
    String? group,
    int limit = TagApiDefaults.suggestLimit,
  }) {
    final params = <String, String>{'q': query, 'limit': '$limit'};
    if (group != null) params['group'] = group;
    return _getList(
      TagApiMetadata.suggestTagsPath,
      TagRequestPageIds.suggestTags,
      TagSuggestion.fromJson,
      params,
    );
  }

  @override
  Future<TagValidationResult> validateRefs(List<String> tagRefs) => _postObject(
    TagApiMetadata.validateTagRefsPath,
    TagRequestPageIds.validateTagRefs,
    <String, dynamic>{'tagRefs': tagRefs},
    TagValidationResult.fromJson,
  );

  @override
  Future<List<TagSearchResult>> search(
    String query, {
    String? group,
    int limit = TagApiDefaults.searchLimit,
  }) {
    final params = <String, String>{'q': query, 'limit': '$limit'};
    if (group != null) params['group'] = group;
    return _getList(
      TagApiMetadata.searchTagsPath,
      TagRequestPageIds.searchTags,
      TagSearchResult.fromJson,
      params,
    );
  }

  @override
  Future<List<RelatedTag>> related(
    String tagRef, {
    int limit = TagApiDefaults.relatedLimit,
  }) => _getList(
    TagApiMetadata.relatedTagsPath,
    TagRequestPageIds.relatedTags,
    RelatedTag.fromJson,
    <String, String>{'tagRef': tagRef, 'limit': '$limit'},
  );
}

/// TagGraphQuery 的 production Remote adapter。
final class RemoteTagGraphQuery extends _TagRemoteTransport
    implements TagGraphQuery {
  RemoteTagGraphQuery({super.httpClient});

  @override
  Future<List<TagObjectMatch>> searchByTags(
    List<String> tagRefs, {
    String? objectType,
    int limit = TagApiDefaults.searchLimit,
  }) {
    final body = <String, dynamic>{'tagRefs': tagRefs, 'limit': limit};
    if (objectType != null) body['objectType'] = objectType;
    return _postList(
      TagApiMetadata.searchByTagsPath,
      TagRequestPageIds.searchByTags,
      body,
      TagObjectMatch.fromJson,
    );
  }

  @override
  Future<List<TagCooccurrence>> cooccurrence({
    String? tagRef,
    int minCount = TagApiDefaults.minCooccurCount,
    int limit = TagApiDefaults.graphLimit,
  }) {
    final params = <String, String>{'minCount': '$minCount', 'limit': '$limit'};
    if (tagRef != null) params['tagRef'] = tagRef;
    return _getList(
      TagApiMetadata.tagCooccurrencePath,
      TagRequestPageIds.tagCooccurrence,
      TagCooccurrence.fromJson,
      params,
    );
  }

  @override
  Future<TagInvertedResult> invertedIndex(
    String tagRef, {
    String? objectType,
    int limit = TagApiDefaults.graphLimit,
  }) {
    final params = <String, String>{'tagRef': tagRef, 'limit': '$limit'};
    if (objectType != null) params['objectType'] = objectType;
    return _getObject(
      TagApiMetadata.invertedObjectsPath,
      TagRequestPageIds.invertedObjects,
      TagInvertedResult.fromJson,
      params,
    );
  }

  @override
  Future<List<RelatedObject>> relatedObjects(
    String objectId, {
    String? objectType,
    int limit = TagApiDefaults.relatedLimit,
  }) {
    final params = <String, String>{'objectId': objectId, 'limit': '$limit'};
    if (objectType != null) params['objectType'] = objectType;
    return _getList(
      TagApiMetadata.relatedObjectsPath,
      TagRequestPageIds.relatedObjects,
      RelatedObject.fromJson,
      params,
    );
  }

  @override
  Future<List<SharedTagView>> sharedTags({
    required String objectAId,
    required String objectAType,
    required String objectBId,
    required String objectBType,
    int limit = TagApiDefaults.graphLimit,
  }) {
    final params = <String, String>{
      'objectAId': objectAId,
      'objectAType': objectAType,
      'objectBId': objectBId,
      'objectBType': objectBType,
      'limit': '$limit',
    };
    return _getList(
      TagApiMetadata.sharedTagsPath,
      TagRequestPageIds.sharedTags,
      SharedTagView.fromJson,
      params,
    );
  }
}
