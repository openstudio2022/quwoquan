import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// 用户拉黑 Repository（三层模式：Abstract → Mock → Remote）
///
/// 对应云侧路由（contracts/metadata/user/block_edge/service.yaml）：
///   POST   /v1/user/block/{targetUserId}
///   DELETE /v1/user/block/{targetUserId}
abstract class BlockRepository {
  Future<void> blockUser(String targetUserId);
  Future<void> unblockUser(String targetUserId);
  bool isBlocked(String targetUserId);
}

/// Mock 实现：本地记录，不发 HTTP 请求。
class MockBlockRepository extends BlockRepository {
  final Set<String> blockedUsers = <String>{};

  @override
  Future<void> blockUser(String targetUserId) async => blockedUsers.add(targetUserId);

  @override
  Future<void> unblockUser(String targetUserId) async => blockedUsers.remove(targetUserId);

  @override
  bool isBlocked(String targetUserId) => blockedUsers.contains(targetUserId);
}

/// Remote 实现：调用云侧 API。
class RemoteBlockRepository extends BlockRepository {
  RemoteBlockRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  })  : _httpClient = httpClient ?? CloudHttpClient(client: client ?? http.Client()),
        _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
        _localCache = <String>{};

  final CloudHttpClient _httpClient;
  final String _baseUrl;
  // 本地缓存已拉黑的用户 ID，避免每次查询都发 HTTP
  final Set<String> _localCache;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<void> blockUser(String targetUserId) async {
    final uri = _uri(UserApiMetadata.blockUserPath(targetUserId: targetUserId));
    try {
      await _httpClient.postJson(
        uri,
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.blockUser),
        body: const <String, dynamic>{},
      );
      _localCache.add(targetUserId);
    } catch (_) {
      // 保持乐观：即使网络失败，本地已记录
      _localCache.add(targetUserId);
      rethrow;
    }
  }

  @override
  Future<void> unblockUser(String targetUserId) async {
    final uri = _uri(
      UserApiMetadata.unblockUserPath(targetUserId: targetUserId),
    );
    try {
      await _httpClient.deleteJson(
        uri,
        headers: CloudRequestHeaders.forPage(UserRequestPageIds.unblockUser),
      );
      _localCache.remove(targetUserId);
    } catch (_) {
      _localCache.remove(targetUserId);
      rethrow;
    }
  }

  @override
  bool isBlocked(String targetUserId) => _localCache.contains(targetUserId);
}
