import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/user/mock/user_profile_mock_data.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

/// 用户主页 Repository。
///
/// 接口方法与将来 contracts/metadata/user/service.yaml routes 一一对应。
/// 待 service.yaml 冻结后通过 make codegen 生成骨架，当前手写。
abstract class UserProfileRepository {
  Future<List<PostBaseDto>> listUserPosts(String userId, {int limit = 20});
  Future<List<UserWorkItem>> listUserWorks(String userId);
  Future<List<UserLifeItem>> listUserLifeItems(String userId);
}

// ─── Mock 实现（本地数据，不发 HTTP）──────────────────────────────────────────

class MockUserProfileRepository implements UserProfileRepository {
  const MockUserProfileRepository();

  @override
  Future<List<PostBaseDto>> listUserPosts(String userId, {int limit = 20}) async {
    final posts = UserProfileMockData.userPostsFor(userId);
    return posts.take(limit).toList();
  }

  @override
  Future<List<UserWorkItem>> listUserWorks(String userId) async {
    return UserProfileMockData.worksFor(userId);
  }

  @override
  Future<List<UserLifeItem>> listUserLifeItems(String userId) async {
    return UserProfileMockData.lifeItemsFor(userId);
  }
}

// ─── Remote 实现（调用云侧 API）───────────────────────────────────────────────

class RemoteUserProfileRepository implements UserProfileRepository {
  RemoteUserProfileRepository({http.Client? client})
      : _client = client ?? http.Client();

  final http.Client _client;

  @override
  Future<List<PostBaseDto>> listUserPosts(String userId, {int limit = 20}) async {
    final url = Uri.parse(
      '${CloudRuntimeConfig.gatewayBaseUrl}/v1/users/$userId/posts?limit=$limit',
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage('user.posts'),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserPosts failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = (data['items'] as List? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return items.map(postBaseDtoFromMap).toList();
  }

  @override
  Future<List<UserWorkItem>> listUserWorks(String userId) async {
    final url = Uri.parse(
      '${CloudRuntimeConfig.gatewayBaseUrl}/v1/users/$userId/works',
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage('user.works'),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserWorks failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = (data['items'] as List? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return items.map(_workItemFromMap).toList();
  }

  @override
  Future<List<UserLifeItem>> listUserLifeItems(String userId) async {
    final url = Uri.parse(
      '${CloudRuntimeConfig.gatewayBaseUrl}/v1/users/$userId/life-items',
    );
    final resp = await _client.get(
      url,
      headers: CloudRequestHeaders.forPage('user.lifeItems'),
    );
    if (resp.statusCode != 200) {
      throw Exception('listUserLifeItems failed: ${resp.statusCode}');
    }
    final data = json.decode(resp.body) as Map<String, dynamic>;
    final items = (data['items'] as List? ?? <dynamic>[])
        .cast<Map<String, dynamic>>();
    return items.map(_lifeItemFromMap).toList();
  }

  static UserWorkItem _workItemFromMap(Map<String, dynamic> m) {
    return UserWorkItem(
      id: m['id']?.toString() ?? '',
      type: m['type']?.toString() ?? '',
      title: m['title']?.toString() ?? '',
      coverUrl: m['coverUrl']?.toString() ?? '',
      likeCount: (m['likeCount'] as num?)?.toInt() ?? 0,
      date: m['date']?.toString() ?? '',
      desc: m['desc']?.toString() ?? '',
    );
  }

  static UserLifeItem _lifeItemFromMap(Map<String, dynamic> m) {
    return UserLifeItem(
      id: m['id']?.toString() ?? '',
      name: m['name']?.toString() ?? '',
      category: m['category']?.toString() ?? '',
      categoryKey: m['categoryKey']?.toString() ?? '',
      coverUrl: m['coverUrl']?.toString() ?? '',
      desc: m['desc']?.toString() ?? '',
    );
  }
}
