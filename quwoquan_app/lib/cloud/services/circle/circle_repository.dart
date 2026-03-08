import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';

/// Circle 域 Repository（三层模式：Abstract + Mock + Remote）。
///
/// Mock：使用 [CircleMockData]（canonical 字段数据），不发 HTTP。
/// Remote：对接云侧 REST 契约，使用 [CloudRuntimeConfig] + [CloudRequestHeaders]。
abstract class CircleRepository {
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
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
    int limit = 20,
  });

  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  );

  Future<List<Map<String, dynamic>>> getCircleFeed(
    String circleId, {
    String? cursor,
    int limit = 20,
    String sort = 'latest',
  });

  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  });

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
    int limit = 20,
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
    int limit = 20,
  });
}

// ---------------------------------------------------------------------------
// Mock
// ---------------------------------------------------------------------------

class MockCircleRepository implements CircleRepository {
  @override
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
  }) async {
    var result = CircleMockData.circles;
    if (category != null) {
      result = result
          .where((c) => c['categoryId'] == category)
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
    int limit = 20,
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
    String? cursor,
    int limit = 20,
    String sort = 'latest',
  }) async {
    return <Map<String, dynamic>>[];
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
    int limit = 20,
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
    int limit = 20,
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

  // -- Circles ---------------------------------------------------------------

  @override
  Future<List<Map<String, dynamic>>> listCircles({
    String? category,
    String? domainId,
    String? recommendFor,
    String? cursor,
    int limit = 20,
    String? sort,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (category != null) query['category'] = category;
    if (domainId != null) query['domainId'] = domainId;
    if (recommendFor != null) query['recommendFor'] = recommendFor;
    if (cursor != null) query['cursor'] = cursor;
    if (sort != null) query['sort'] = sort;

    final uri = Uri.parse('$_baseUrl/v1/circles')
        .replace(queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.list'),
    );
    return _decodeList(resp);
  }

  @override
  Future<Map<String, dynamic>> getCircle(String circleId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}',
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.get'),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> createCircle(Map<String, dynamic> data) async {
    final uri = Uri.parse('$_baseUrl/v1/circles');
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.create'),
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
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}',
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.update'),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> archiveCircle(String circleId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}',
    );
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage('circle.archive'),
    );
    _ensureSuccess(resp);
  }

  // -- Membership ------------------------------------------------------------

  @override
  Future<void> joinCircle(String circleId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/join',
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage('circle.join'),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<void> leaveCircle(String circleId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/leave',
    );
    final resp = await _client.post(
      uri,
      headers: CloudRequestHeaders.forPage('circle.leave'),
    );
    _ensureSuccess(resp);
  }

  @override
  Future<List<Map<String, dynamic>>> listMembers(
    String circleId, {
    String? cursor,
    int limit = 20,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/members',
    ).replace(queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.members.list'),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> updateMemberRole(
    String circleId,
    String userId,
    String role,
  ) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/members/${Uri.encodeComponent(userId)}/role',
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.members.updateRole'),
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
    String? cursor,
    int limit = 20,
    String sort = 'latest',
  }) async {
    final query = <String, String>{'limit': '$limit', 'sort': sort};
    if (cursor != null) query['cursor'] = cursor;

    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/feed',
    ).replace(queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.feed.list'),
    );
    return _decodeList(resp);
  }

  @override
  Future<void> pinPost(
    String circleId,
    String postId, {
    required bool pinned,
  }) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/feed/${Uri.encodeComponent(postId)}/pin',
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.post.pin'),
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
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/feed/${Uri.encodeComponent(postId)}/feature',
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.post.feature'),
        'Content-Type': 'application/json',
      },
      body: json.encode({'featured': featured}),
    );
    _ensureSuccess(resp);
  }

  // -- Stats -----------------------------------------------------------------

  @override
  Future<Map<String, dynamic>> getCircleStats(String circleId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/stats',
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.stats'),
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
    int limit = 20,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (parentId != null) query['parentId'] = parentId;
    if (sort != null) query['sort'] = sort;
    if (cursor != null) query['cursor'] = cursor;

    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/files',
    ).replace(queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.files.list'),
    );
    return _decodeList(resp);
  }

  @override
  Future<Map<String, dynamic>> createFile(
    String circleId,
    Map<String, dynamic> data,
  ) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/files',
    );
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.files.create'),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> getFile(String circleId, String fileId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/files/${Uri.encodeComponent(fileId)}',
    );
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.files.get'),
    );
    return _decodeObject(resp);
  }

  @override
  Future<Map<String, dynamic>> updateFile(
    String circleId,
    String fileId,
    Map<String, dynamic> data,
  ) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/files/${Uri.encodeComponent(fileId)}',
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.files.update'),
        'Content-Type': 'application/json',
      },
      body: json.encode(data),
    );
    return _decodeObject(resp);
  }

  @override
  Future<void> deleteFile(String circleId, String fileId) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/files/${Uri.encodeComponent(fileId)}',
    );
    final resp = await _client.delete(
      uri,
      headers: CloudRequestHeaders.forPage('circle.files.delete'),
    );
    _ensureSuccess(resp);
  }

  // -- Sections --------------------------------------------------------------

  @override
  Future<void> updateSections(
    String circleId,
    List<Map<String, dynamic>> sections,
  ) async {
    final uri = Uri.parse(
      '$_baseUrl/v1/circles/${Uri.encodeComponent(circleId)}/sections',
    );
    final resp = await _client.patch(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.sections.update'),
        'Content-Type': 'application/json',
      },
      body: json.encode({'sections': sections}),
    );
    _ensureSuccess(resp);
  }

  // -- Behavior --------------------------------------------------------------

  @override
  Future<void> reportBehavior(Map<String, dynamic> report) async {
    final uri = Uri.parse('$_baseUrl/v1/circles/behaviors');
    final resp = await _client.post(
      uri,
      headers: {
        ...CloudRequestHeaders.forPage('circle.behaviors.report'),
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
    int limit = 20,
  }) async {
    final query = <String, String>{'limit': '$limit'};
    if (cursor != null) query['cursor'] = cursor;

    final uri = Uri.parse(
      '$_baseUrl/v1/users/${Uri.encodeComponent(userId)}/circles',
    ).replace(queryParameters: query);
    final resp = await _client.get(
      uri,
      headers: CloudRequestHeaders.forPage('circle.user.list'),
    );
    return _decodeList(resp);
  }

  // -- Helpers ---------------------------------------------------------------

  void _ensureSuccess(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw Exception(
        'Circle API error ${resp.statusCode}: ${resp.body}',
      );
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
