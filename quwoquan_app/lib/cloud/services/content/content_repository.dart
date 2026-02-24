import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/generated/post_runtime_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/core/services/data_service.dart';

/// Content 域 Repository（端侧按业务对象组织的统一入口）。
///
/// - Mock：复用现有 DataServiceImpl 的原型数据，保证 UI 不被大规模改动。
/// - Remote：对接云侧 Gateway/Orchestrator 的 REST 契约（OpenAPI）。
abstract class ContentRepository {
  Future<CursorPage<Map<String, dynamic>>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  });

  Future<List<Map<String, dynamic>>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  });

  Future<Map<String, dynamic>> getPost({
    required String postId,
  });

  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  });
}

class MockContentRepository implements ContentRepository {
  MockContentRepository({DataService? dataService})
      : _dataService = dataService ?? DataServiceImpl();

  final DataService _dataService;

  @override
  Future<CursorPage<Map<String, dynamic>>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final items = await _dataService.getDataList(
      endpoint: '/posts',
      params: <String, dynamic>{
        'category': category,
        'subCategory': subCategory,
        'cursor': cursor,
      },
      limit: limit,
    );
    return CursorPage<Map<String, dynamic>>(
      items: items,
      nextCursor: null,
    );
  }

  @override
  Future<List<Map<String, dynamic>>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
    );
    return page.items;
  }

  @override
  Future<Map<String, dynamic>> getPost({
    required String postId,
  }) {
    return _dataService.getDataItem(endpoint: '/posts', id: postId);
  }

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) {
    return _dataService.createDataItem(endpoint: '/posts', data: payload);
  }
}

class RemoteContentRepository implements ContentRepository {
  RemoteContentRepository({
    CloudHttpClient? httpClient,
    http.Client? client,
    String? baseUrl,
  }) : _httpClient =
           httpClient ?? CloudHttpClient(client: client ?? http.Client()),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<CursorPage<Map<String, dynamic>>> listDiscoveryFeedPage({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    // 路径、参数由 metadata codegen 产物统一提供，避免端侧硬编码。
    final type = _mapCategoryToFeedType(category);
    final c = cursor;
    final sub = subCategory;
    final query = <String, String>{};
    final keys = GeneratedPostRuntimeMetadata.feedQueryParams;
    if (keys.contains('type') && type != null && type.isNotEmpty) {
      query['type'] = type;
    }
    if (keys.contains('cursor') && c?.isNotEmpty == true) {
      query['cursor'] = c!;
    }
    if (keys.contains('limit')) {
      query['limit'] = '$limit';
    }
    if (keys.contains('subCategory') && sub?.isNotEmpty == true) {
      query['subCategory'] = sub!;
    }
    final uri = Uri.parse('$_baseUrl${GeneratedPostRuntimeMetadata.feedPath}').replace(
      queryParameters: query,
    );
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.feed.list'),
    );
    return CloudResponseDecoder.asCursorPage(
      decoded,
      context: 'content.feed.list',
    );
  }

  @override
  Future<List<Map<String, dynamic>>> listDiscoveryFeed({
    required String category,
    String? subCategory,
    int limit = GeneratedPostRuntimeMetadata.feedDefaultLimit,
    String? cursor,
  }) async {
    final page = await listDiscoveryFeedPage(
      category: category,
      subCategory: subCategory,
      limit: limit,
      cursor: cursor,
    );
    return page.items;
  }

  @override
  Future<Map<String, dynamic>> getPost({
    required String postId,
  }) async {
    final path = GeneratedPostRuntimeMetadata.postDetailPathTemplate.replaceAll(
      '{postId}',
      Uri.encodeComponent(postId),
    );
    final uri = Uri.parse('$_baseUrl$path');
    final decoded = await _httpClient.getJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.get'),
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.get');
  }

  @override
  Future<Map<String, dynamic>> createPost({
    required Map<String, dynamic> payload,
  }) async {
    final uri = Uri.parse('$_baseUrl/v1/content/posts');
    final decoded = await _httpClient.postJson(
      uri,
      headers: CloudRequestHeaders.forPage('content.post.create'),
      body: payload,
    );
    return CloudResponseDecoder.asObject(decoded, context: 'content.post.create');
  }

  String? _mapCategoryToFeedType(String category) {
    return GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
  }
}

