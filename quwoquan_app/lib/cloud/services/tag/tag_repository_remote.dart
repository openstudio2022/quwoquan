part of 'tag_repository.dart';

/// Remote 实现 — 调用云侧 Tag API。
/// path / pageId 全部来自 codegen 真相源（TagApiMetadata / TagRequestPageIds），
/// 不得硬编码 /api/v1/tags/* 路径（军规 R06/R09）。
///
/// 解码统一经 [CloudResponseDecoder]，私有泛型中转 `_getList/_getObject/_postList/
/// _postObject` 直出强类型聚合实体 DTO，不暴露裸 `dynamic`/`Object?` 作业务契约
/// （StrictTyping，见 cloud_map_typing_audit_anchor.dart）；`Object?` 仅作解码入口
/// 局部参数，下一跳即转 DTO 或 [CloudJsonMap]。门禁见 verify_cloud_tag_strict_typing.py。
class RemoteTagRepository implements TagRepository {
  final CloudHttpClient _httpClient;

  RemoteTagRepository({CloudHttpClient? httpClient})
    : _httpClient = httpClient ?? CloudHttpClient();

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
  Future<bool> feedback(String tagRef, String action, {String? context}) async {
    final body = <String, dynamic>{'tagRef': tagRef, 'action': action};
    if (context != null) body['context'] = context;
    final obj = await _postObject<CloudJsonMap>(
      TagApiMetadata.tagFeedbackPath,
      TagRequestPageIds.tagFeedback,
      body,
      (m) => m,
    );
    return obj['accepted'] == true;
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
