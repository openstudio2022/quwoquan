part of 'tag_repository.dart';

/// Remote 实现 — 调用云侧 Tag API
class RemoteTagRepository implements TagRepository {
  final http.Client _client;

  RemoteTagRepository({http.Client? client}) : _client = client ?? http.Client();

  Uri _uri(String path, [Map<String, String>? params]) =>
      Uri.parse('${CloudRuntimeConfig.gatewayBaseUrl}$path')
          .replace(queryParameters: params);

  Map<String, String> get _headers => CloudRequestHeaders.standard();

  Future<dynamic> _get(String path, [Map<String, String>? params]) async {
    final resp = await _client.get(_uri(path, params), headers: _headers);
    if (resp.statusCode != 200) {
      throw Exception('Tag API error: ${resp.statusCode} ${resp.body}');
    }
    return json.decode(resp.body);
  }

  Future<dynamic> _post(String path, Map<String, dynamic> body) async {
    final resp = await _client.post(
      _uri(path),
      headers: {..._headers, 'Content-Type': 'application/json'},
      body: json.encode(body),
    );
    if (resp.statusCode != 200) {
      throw Exception('Tag API error: ${resp.statusCode} ${resp.body}');
    }
    return json.decode(resp.body);
  }

  @override
  Future<List<TagDimension>> listDimensions() async {
    final data = await _get('/api/v1/tags/dimensions') as List;
    return data.map((e) => TagDimension.fromJson(e as Map<String, dynamic>)).toList();
  }

  @override
  Future<List<TagSuggestion>> suggest(String query,
      {String? group, int limit = 20}) async {
    final params = <String, String>{'q': query, 'limit': '$limit'};
    if (group != null) params['group'] = group;
    final data = await _get('/api/v1/tags/suggest', params) as List;
    return data.map((e) => TagSuggestion.fromJson(e as Map<String, dynamic>)).toList();
  }

  @override
  Future<TagValidationResult> validateRefs(List<String> tagRefs) async {
    final data = await _post('/api/v1/tags/validate', {'tagRefs': tagRefs});
    return TagValidationResult.fromJson(data as Map<String, dynamic>);
  }

  @override
  Future<List<TagSearchResult>> search(String query,
      {String? group, int limit = 50}) async {
    final params = <String, String>{'q': query, 'limit': '$limit'};
    if (group != null) params['group'] = group;
    final data = await _get('/api/v1/tags/search', params) as List;
    return data.map((e) => TagSearchResult.fromJson(e as Map<String, dynamic>)).toList();
  }

  @override
  Future<List<RelatedTag>> related(String tagRef, {int limit = 20}) async {
    final encoded = Uri.encodeComponent(tagRef);
    final data = await _get('/api/v1/tags/$encoded/related',
        {'limit': '$limit'}) as List;
    return data.map((e) => RelatedTag.fromJson(e as Map<String, dynamic>)).toList();
  }

  @override
  Future<List<TagObjectMatch>> searchByTags(List<String> tagRefs,
      {String? objectType, int limit = 50}) async {
    final body = <String, dynamic>{'tagRefs': tagRefs, 'limit': limit};
    if (objectType != null) body['objectType'] = objectType;
    final data = await _post('/api/v1/tags/search-by-tags', body) as List;
    return data.map((e) => TagObjectMatch.fromJson(e as Map<String, dynamic>)).toList();
  }

  @override
  Future<bool> feedback(String tagRef, String action, {String? context}) async {
    final body = <String, dynamic>{'tagRef': tagRef, 'action': action};
    if (context != null) body['context'] = context;
    final data = await _post('/api/v1/tags/feedback', body);
    return (data as Map<String, dynamic>)['accepted'] == true;
  }

  @override
  Future<List<TagCooccurrence>> cooccurrence(
      {String? tagRef, int minCount = 1, int limit = 50}) async {
    final params = <String, String>{
      'minCount': '$minCount',
      'limit': '$limit',
    };
    if (tagRef != null) params['tagRef'] = tagRef;
    final data = await _get('/api/v1/tags/graph/cooccurrence', params) as List;
    return data.map((e) => TagCooccurrence.fromJson(e as Map<String, dynamic>)).toList();
  }

  @override
  Future<TagInvertedResult> invertedIndex(String tagRef,
      {String? objectType, int limit = 50}) async {
    final encoded = Uri.encodeComponent(tagRef);
    final params = <String, String>{'limit': '$limit'};
    if (objectType != null) params['objectType'] = objectType;
    final data = await _get('/api/v1/tags/graph/inverted-index/$encoded', params);
    return TagInvertedResult.fromJson(data as Map<String, dynamic>);
  }

  @override
  Future<List<RelatedObject>> relatedObjects(String objectId,
      {String? objectType, int limit = 20}) async {
    final encoded = Uri.encodeComponent(objectId);
    final params = <String, String>{'limit': '$limit'};
    if (objectType != null) params['objectType'] = objectType;
    final data = await _get('/api/v1/tags/graph/related-objects/$encoded', params) as List;
    return data.map((e) => RelatedObject.fromJson(e as Map<String, dynamic>)).toList();
  }
}
