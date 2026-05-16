import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// 内容互动 Repository（三层模式：Abstract → Mock → Remote）
///
/// 对应云侧路由（contracts/metadata/content/post/service.yaml）：
///   POST   /v1/content/posts/{postId}/like
///   DELETE /v1/content/posts/{postId}/like
///   POST   /v1/content/posts/{postId}/favorite
///   DELETE /v1/content/posts/{postId}/favorite
abstract class ContentInteractionRepository {
  Future<void> like(String postId);
  Future<void> unlike(String postId);
  Future<void> favorite(String postId);
  Future<void> unfavorite(String postId);
}

/// Mock 实现：本地记录状态，不发 HTTP 请求。
class MockContentInteractionRepository extends ContentInteractionRepository {
  final Set<String> likedPosts = <String>{};
  final Set<String> favoritedPosts = <String>{};

  @override
  Future<void> like(String postId) async => likedPosts.add(postId);

  @override
  Future<void> unlike(String postId) async => likedPosts.remove(postId);

  @override
  Future<void> favorite(String postId) async => favoritedPosts.add(postId);

  @override
  Future<void> unfavorite(String postId) async => favoritedPosts.remove(postId);
}

/// Remote 实现：调用云侧 API。
class RemoteContentInteractionRepository extends ContentInteractionRepository {
  RemoteContentInteractionRepository({
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  Uri _uri(String path) => Uri.parse('$_baseUrl$path');

  @override
  Future<void> like(String postId) async {
    final uri = _uri(ContentApiMetadata.likePostPath(postId: postId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.likePost),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> unlike(String postId) async {
    final uri = _uri(ContentApiMetadata.unlikePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.unlikePost),
    );
  }

  @override
  Future<void> favorite(String postId) async {
    final uri = _uri(ContentApiMetadata.favoritePostPath(postId: postId));
    await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage(ContentRequestPageIds.favoritePost),
      body: const <String, dynamic>{},
    );
  }

  @override
  Future<void> unfavorite(String postId) async {
    final uri = _uri(ContentApiMetadata.unfavoritePostPath(postId: postId));
    await _httpClient.deleteJson(
      uri,
      headers: CloudRequestHeaders.forPage(
        ContentRequestPageIds.unfavoritePost,
      ),
    );
  }
}
