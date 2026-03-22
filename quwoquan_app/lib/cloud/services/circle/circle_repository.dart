import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_app/core/models/search_models.dart';

String? _normalizeCircleFeedType(String? type) {
  final normalized = (type ?? '').trim().toLowerCase();
  switch (normalized) {
    case '':
      return null;
    case 'photo':
      return 'image';
    case 'note':
      return 'article';
    default:
      return normalized;
  }
}

/// Circle 域 Repository（三层模式：Abstract + Mock + Remote）。
///
/// Mock：使用 [CircleMockData]（canonical 字段数据），不发 HTTP。
/// Remote：对接云侧 REST 契约，使用 [CloudRuntimeConfig] + [CloudRequestHeaders]。
abstract class CircleRepository {
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  });

  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<Map<String, dynamic>> getCircle(String circleId);

  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data);

  Future<Map<String, dynamic>> updateCircle(
    String circleId,
    Map<String, dynamic> data,
  );

  Future<void> archiveCircle(String circleId);

  Future<void> joinCircle(String circleId);

  Future<void> leaveCircle(String circleId);

  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<void> updateMemberRole(String circleId, String userId, String role);

  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  });

  Future<void> pinPost(String circleId, String postId, {required bool pinned});

  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  });

  Future<Map<String, dynamic>> getCircleStats(String circleId);

  Future<List<Map<String, dynamic>>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });

  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  );

  Future<Map<String, dynamic>> getFile(String circleId, String fileId);

  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  );

  Future<void> deleteFile(String circleId, String fileId);

  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  );

  Future<void> reportBehavior(Map<String, dynamic> report);

  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  });
}

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

class MockCircleRepository implements CircleRepository {
  @override
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  }) async {
    var result = CircleMockData.circles;
    if (category != null) {
      result = result
          .where((c) => c['categoryId'] == category)
          .toList(growable: false);
    }
    if (subCategory != null) {
      result = result
          .where((c) => c['subCategory'] == subCategory)
          .toList(growable: false);
    }
    if (domainId != null) {
      result = result
          .where((c) => c['domainId'] == domainId)
          .toList(growable: false);
    }
    return result.take(limit).toList(growable: false);
  }

  @override
  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedQuery.isEmpty) {
      return const CircleSearchResultView();
    }
    final filtered = CircleMockData.circles.where((circle) {
      if (categoryId != null &&
          categoryId.isNotEmpty &&
          circle['categoryId']?.toString() != categoryId) {
        return false;
      }
      if (subCategory != null &&
          subCategory.isNotEmpty &&
          circle['subCategory']?.toString() != subCategory) {
        return false;
      }
      final name = (circle['name'] ?? '').toString().toLowerCase();
      final description = (circle['description'] ?? '').toString().toLowerCase();
      return name.contains(normalizedQuery) ||
          description.contains(normalizedQuery);
    }).toList(growable: false);
    final items = filtered
        .take(limit)
        .map((circle) {
          final name = (circle['name'] ?? '').toString();
          return CircleSearchItemView.fromMap(<String, dynamic>{
            ...circle,
            'circleId': circle['circleId'] ?? circle['id'],
            'highlightText': name,
            'matchedField': 'name',
          });
        })
        .toList(growable: false);
    final facetCounts = <String, int>{};
    for (final circle in filtered) {
      final key = (circle['subCategory'] ?? circle['categoryId'] ?? '')
          .toString()
          .trim();
      if (key.isEmpty) {
        continue;
      }
      facetCounts.update(key, (value) => value + 1, ifAbsent: () => 1);
    }
    final facetBuckets = filtered
        .map((circle) => <String, dynamic>{
          'facetKey': (circle['subCategory'] ?? circle['categoryId'] ?? '')
              .toString(),
          'label': (circle['subCategory'] ?? circle['categoryId'] ?? '')
              .toString(),
          'categoryId': circle['categoryId']?.toString(),
          'subCategory': circle['subCategory']?.toString(),
        })
        .where((facet) => (facet['facetKey'] ?? '').toString().isNotEmpty)
        .fold<Map<String, Map<String, dynamic>>>(
          <String, Map<String, dynamic>>{},
          (accumulator, facet) {
            accumulator.putIfAbsent(
              facet['facetKey']!.toString(),
              () => <String, dynamic>{
                ...facet,
                'facetCount': facetCounts[facet['facetKey']] ?? 0,
              },
            );
            return accumulator;
          },
        )
        .values
        .map(CircleFacetBucketView.fromMap)
        .toList(growable: false);
    return CircleSearchResultView(items: items, facetBuckets: facetBuckets);
  }

  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    if (circleId == CircleMockData.circleInfo['id']) {
      return CircleMockData.circleInfo;
    }
    final match = CircleMockData.circles.firstWhere(
      (c) => c['id'] == circleId,
      orElse: () => <String, dynamic>{},
    );
    if (match.isEmpty) {
      return Future.error(Exception('Circle $circleId not found'));
    }
    return match;
  }

  @override
  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data) async {
    return <String, dynamic>{
      ...data,
      'id': 'local_${DateTime.now().millisecondsSinceEpoch}',
      'createdAt': DateTime.now().toIso8601String(),
    };
  }

  @override
  Future<Map<String, dynamic>> updateCircle(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final existing = await getCircle(circleId);
    return <String, dynamic>{...existing, ...data};
  }

  @override
  Future<void> archiveCircle(String circleId) async {}

  @override
  Future<void> joinCircle(String circleId) async {}

  @override
  Future<void> leaveCircle(String circleId) async {}

  @override
  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return CircleMockData.members.take(limit).toList(growable: false);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {}

  @override
  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  }) async {
    final normalizedType = _normalizeCircleFeedType(type);
    return CircleMockData.circleFeedItems
        .where((item) => item['circleId'] == circleId)
        .where((item) {
          if (identity != null && identity.isNotEmpty) {
            if ((item['contentIdentity'] ?? '').toString() != identity) {
              return false;
            }
          }
          if (normalizedType != null && normalizedType.isNotEmpty) {
            final itemType = _normalizeCircleFeedType(
              item['contentType']?.toString() ?? item['type']?.toString(),
            );
            return itemType == normalizedType;
          }
          return true;
        })
        .take(limit)
        .map((item) => Map<String, dynamic>.from(item))
        .toList(growable: false);
  }

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {}

  @override
  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  }) async {}

  @override
  Future<Map<String, dynamic>> getCircleStats(String circleId) async {
    return CircleMockData.stats;
  }

  @override
  Future<List<Map<String, dynamic>>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    var result = CircleMockData.files;
    if (parentId != null) {
      result = result
          .where((f) => f['parentId'] == parentId)
          .toList(growable: false);
    }
    return result.take(limit).toList(growable: false);
  }

  @override
  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    return <String, dynamic>{
      ...data,
      'id': 'f_${DateTime.now().millisecondsSinceEpoch}',
      'createdAt': DateTime.now().toIso8601String(),
    };
  }

  @override
  Future<Map<String, dynamic>> getFile(String circleId, String fileId) async {
    final match = CircleMockData.files.firstWhere(
      (f) => f['id'] == fileId,
      orElse: () => <String, dynamic>{},
    );
    if (match.isEmpty) {
      return Future.error(Exception('File $fileId not found'));
    }
    return match;
  }

  @override
  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  ) async {
    final existing = await getFile(circleId, fileId);
    return <String, dynamic>{...existing, ...data};
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {}

  @override
  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  ) async {}

  @override
  Future<void> reportBehavior(Map<String, dynamic> report) async {}

  @override
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    return CircleMockData.circles.take(limit).toList(growable: false);
  }
}

// ---------------------------------------------------------------------------
// Remote
// ---------------------------------------------------------------------------

class RemoteCircleRepository implements CircleRepository {
  RemoteCircleRepository({http.Client? client, String? baseUrl})
    : _client = client ?? http.Client(),
      _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final http.Client _client;
  final String _baseUrl;

  Uri _uri(String path, {Map<String, String>? queryParameters}) {
    return Uri.parse(
      '$_baseUrl$path',
    ).replace(queryParameters: queryParameters);
  }

  // -- Circles ---------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? subCategory,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String? sort,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (category != null) query['category'] = category;
    if (subCategory != null) query['subCategory'] = subCategory;
    if (domainId != null) query['domainId'] = domainId;
    if (recommendFor != null) query['recommendFor'] = recommendFor;
    if (cursor != null) query['cursor'] = cursor;
    if (sort != null) query['sort'] = sort;

    final uri = _uri(CircleApiMetadata.listCirclesPath, queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.listCircles),
    );
    return _decodeList(resp);
  }

  @override
  Future<CircleSearchResultView> searchCircles({
    required String query,
    String? categoryId,
    String? subCategory,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final resp = await _client.get(
      _uri(
        CircleApiMetadata.searchCirclesPath,
        queryParameters: <String, String>{
          'query': query,
          if (categoryId != null && categoryId.isNotEmpty)
            'categoryId': categoryId,
          if (subCategory != null && subCategory.isNotEmpty)
            'subCategory': subCategory,
          'limit': '$limit',
        },
      ),
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.searchCircles),
    );
    return CircleSearchResultView.fromMap(_decodeObject(resp));
  }

  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.getCirclePath(circleId: circleId));
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircle),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data) async {
    final uri = _uri(CircleApiMetadata.createCirclePath);
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircle),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> updateCircle(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(CircleApiMetadata.updateCirclePath(circleId: circleId));
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircle),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> archiveCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.archiveCirclePath(circleId: circleId));
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.archiveCircle),
    );
    _ensureSuccess(resp);
  }

  // -- Membership ------------------------------------------------------------

  @override
  Future<void> joinCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.joinCirclePath(circleId: circleId));
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.joinCircle),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> leaveCircle(String circleId) async {
    final uri = _uri(CircleApiMetadata.leaveCirclePath(circleId: circleId));
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.leaveCircle),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listCircleMembersPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleMembers,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateMemberRolePath(
        circleId: circleId,
        userId: userId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateMemberRole),
        'Content-Type': 'application/json',
      },
      body: json.encode({'role': role}),
    );
    _ensureSuccess(resp);
  }

  // -- Feed ------------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? identity,
    String? type,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
    String sort = 'latest',
  }) async {
    final query = <String, String>{'limit': '$limit', 'sort': sort};
    if (cursor != null) query['cursor'] = cursor;
    if (identity != null && identity.isNotEmpty) query['identity'] = identity;
    final normalizedType = _normalizeCircleFeedType(type);
    if (normalizedType != null && normalizedType.isNotEmpty) {
      query['type'] = normalizedType;
    }

    final uri = _uri(
      CircleApiMetadata.getCircleFeedPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFeed),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {
    final uri = _uri(
      CircleApiMetadata.pinCirclePostPath(circleId: circleId, postId: postId),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.pinCirclePost),
        'Content-Type': 'application/json',
      },
      body: json.encode({'pinned': pinned}),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> featurePost(
    String circleId,
    String postId, {
    required bool featured,
  }) async {
    final uri = _uri(
      CircleApiMetadata.featureCirclePostPath(
        circleId: circleId,
        postId: postId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.featureCirclePost),
        'Content-Type': 'application/json',
      },
      body: json.encode({'featured': featured}),
    );
    _ensureSuccess(resp);
  }

  // -- Stats -----------------------------------------------------------------

  @override
  Future<Map<String, dynamic>> getCircleStats(String circleId) async {
    final uri = _uri(CircleApiMetadata.getCircleStatsPath(circleId: circleId));
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleStats),
    );
    return _decodeObject(resp);
  }

  // -- Files -----------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listFiles(
    String circleId, {
    String? parentId,
    String? sort,
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (parentId != null) query['parentId'] = parentId;
    if (sort != null) query['sort'] = sort;
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listCircleFilesPath(circleId: circleId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listCircleFiles,
      ),
    );
    return _decodeList(resp);
  }

  @override
  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.createCircleFilePath(circleId: circleId),
    );
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.createCircleFile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> getFile(String circleId, String fileId) async {
    final uri = _uri(
      CircleApiMetadata.getCircleFilePath(circleId: circleId, fileId: fileId),
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(CircleRequestPageIds.getCircleFile),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleFilePath(
        circleId: circleId,
        fileId: fileId,
      ),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(CircleRequestPageIds.updateCircleFile),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {
    final uri = _uri(
      CircleApiMetadata.deleteCircleFilePath(
        circleId: circleId,
        fileId: fileId,
      ),
    );
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.deleteCircleFile,
      ),
    );
    _ensureSuccess(resp);
  }

  // -- Sections --------------------------------------------------------------

  @override
  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  ) async {
    final uri = _uri(
      CircleApiMetadata.updateCircleSectionsPath(circleId: circleId),
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(
          CircleRequestPageIds.updateCircleSections,
        ),
        'Content-Type': 'application/json',
      },
      body: json.encode({'sections': sections}),
    );
    _ensureSuccess(resp);
  }

  // -- Behavior --------------------------------------------------------------

  @override
  Future<void> reportBehavior(Map<String, dynamic> report) async {
    final uri = _uri(CircleApiMetadata.reportCircleBehaviorPath);
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage(
          CircleRequestPageIds.reportCircleBehavior,
        ),
        'Content-Type': 'application/json',
      },
      body: json.encode(report),
    );
    _ensureSuccess(resp);
  }

  // -- User Circles ----------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listUserCircles(
    String userId, {
    String? cursor,
    int limit = CloudApiDefaults.pageLimit,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = _uri(
      CircleApiMetadata.listUserCirclesPath(userId: userId),
      queryParameters: query,
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage(
        CircleRequestPageIds.listUserCircles,
      ),
    );
    return _decodeList(resp);
  }

  // -- Helpers ---------------------------------------------------------------

  void _ensureSuccess(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception('Circle API error ${resp.statusCode}: ${resp.body}');
    }
  }

  Map<String, dynamic> _decodeObject(http.Response resp) {
    _ensureSuccess(resp);
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) {
      return (decoded['data'] as Map<String, dynamic>?) ?? decoded;
    }
    throw FormatException('Expected JSON object, got ${decoded.runtimeType}');
  }

  List<Map<String, dynamic>> _decodeList(http.Response resp) {
    _ensureSuccess(resp);
    final decoded = json.decode(resp.body);
    if (decoded is Map<String, dynamic>) {
      final items = decoded['data'] ?? decoded['items'] ?? [];
      return (items as List).cast<Map<String, dynamic>>();
    }
    if (decoded is List) {
      return decoded.cast<Map<String, dynamic>>();
    }
    throw FormatException('Expected JSON list, got ${decoded.runtimeType}');
  }
}
