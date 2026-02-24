import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/post_runtime_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/features/home/models/user_models.dart';

/// 主题相关的便捷Provider
final isDarkProvider = Provider<bool>((ref) {
  return ref.watch(themeProvider).isDark;
});

/// 用户数据Provider
class UserDataNotifier extends Notifier<User?> {
  @override
  User? build() {
    return null;
  }

  Future<void> loadUser(String username) async {
    // Stub implementation
    state = User(
      id: username,
      username: username,
    );
  }
}

final userDataProvider = NotifierProvider<UserDataNotifier, User?>(() {
  return UserDataNotifier();
});

/// 响应式Provider (stub)
final responsiveProvider = Provider<Map<String, dynamic>>((ref) {
  return {};
});

/// 数据服务Provider
final dataServiceProvider = Provider<DataService>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    // 过渡层：UI 仍可调用 DataService，但底层已经按 ContentRepository（业务对象）组织。
    final repo = ref.watch(contentRepositoryProvider);
    return _LegacyContentDataService(repo);
  }
  return DataServiceImpl();
});

class _LegacyContentDataService implements DataService {
  _LegacyContentDataService(this._contentRepository);

  final ContentRepository _contentRepository;
  final List<Map<String, dynamic>> _localGeneratedPosts = <Map<String, dynamic>>[];

  List<Map<String, dynamic>> _mergeLocalGeneratedPosts({
    required List<Map<String, dynamic>> remoteItems,
    required String category,
  }) {
    final remoteIds = remoteItems
        .map((item) => item['id']?.toString() ?? '')
        .where((id) => id.isNotEmpty)
        .toSet();
    final local = _localGeneratedPosts
        .where(
          (post) =>
              _matchesCategory(post, category) &&
              !remoteIds.contains(post['id']?.toString() ?? ''),
        )
        .toList(growable: false);
    if (local.isEmpty) return remoteItems;
    return <Map<String, dynamic>>[
      ...local,
      ...remoteItems,
    ];
  }

  bool _matchesCategory(Map<String, dynamic> post, String category) {
    final expectedFeedType =
        GeneratedPostRuntimeMetadata.feedCategoryToRequestType[category];
    if (expectedFeedType == null || expectedFeedType.isEmpty) {
      return true;
    }
    final postType = (post['type'] ?? '').toString().trim();
    if (postType.isEmpty) return false;
    final normalizedPostType = switch (postType) {
      'image' => 'photo',
      _ => postType,
    };
    return normalizedPostType == expectedFeedType;
  }

  @override
  Future<List<Map<String, dynamic>>> getDataList({
    required String endpoint,
    Map<String, dynamic>? params,
    int? limit,
    int? offset,
  }) async {
    if (endpoint == '/posts') {
      final category = (params?['category'] as String?) ?? 'recommended';
      final subCategory = params?['subCategory'] as String?;
      final cursor = params?['cursor'] as String?;
      final remoteItems = await _contentRepository.listDiscoveryFeed(
        category: category,
        subCategory: subCategory,
        cursor: cursor,
        limit: limit ?? GeneratedPostRuntimeMetadata.feedDefaultLimit,
      );
      return _mergeLocalGeneratedPosts(
        remoteItems: remoteItems,
        category: category,
      );
    }
    throw UnimplementedError('LegacyDataService endpoint=$endpoint');
  }

  @override
  Future<Map<String, dynamic>> getDataItem({
    required String endpoint,
    required String id,
    Map<String, dynamic>? params,
  }) {
    if (endpoint == '/posts') {
      for (final post in _localGeneratedPosts) {
        if (post['id']?.toString() == id) {
          return Future<Map<String, dynamic>>.value(post);
        }
      }
      return _contentRepository.getPost(postId: id);
    }
    throw UnimplementedError('LegacyDataService getDataItem endpoint=$endpoint');
  }

  @override
  Future<Map<String, dynamic>> createDataItem({
    required String endpoint,
    required Map<String, dynamic> data,
  }) async {
    if (endpoint == '/posts') {
      final remotePost = await _contentRepository.createPost(payload: data);
      _localGeneratedPosts.insert(0, remotePost);
      return remotePost;
    }
    throw UnimplementedError(
      'LegacyDataService createDataItem endpoint=$endpoint',
    );
  }

  @override
  Future<Map<String, dynamic>> updateDataItem({
    required String endpoint,
    required String id,
    required Map<String, dynamic> data,
  }) {
    if (endpoint == '/posts') {
      final index = _localGeneratedPosts.indexWhere(
        (post) => post['id']?.toString() == id,
      );
      if (index < 0) {
        throw UnsupportedError(
          'LegacyDataService updateDataItem only supports local-generated posts: $id',
        );
      }
      final updated = <String, dynamic>{
        ..._localGeneratedPosts[index],
        ...data,
        'updatedAt': DateTime.now().toIso8601String(),
      };
      _localGeneratedPosts[index] = updated;
      return Future<Map<String, dynamic>>.value(updated);
    }
    throw UnimplementedError('LegacyDataService updateDataItem endpoint=$endpoint');
  }

  @override
  Future<void> deleteDataItem({
    required String endpoint,
    required String id,
  }) {
    if (endpoint == '/posts') {
      _localGeneratedPosts.removeWhere((post) => post['id']?.toString() == id);
      return Future<void>.value();
    }
    throw UnimplementedError('LegacyDataService deleteDataItem endpoint=$endpoint');
  }
}

/// 浏览记录服务 Provider（小趣基线：记录访问用于 experienceLevel）
final visitRecorderServiceProvider = Provider<VisitRecorderService>((ref) {
  return VisitRecorderService();
});

/// Content Repository（按业务对象组织的端侧入口）
final contentRepositoryProvider = Provider<ContentRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteContentRepository();
  }
  return MockContentRepository();
});

/// Chat Repository（按业务对象组织的端侧入口）
final chatRepositoryProvider = Provider<ChatRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteChatRepository();
  }
  return MockChatRepository(ref.watch(appContentRepositoryProvider));
});

/// User Repository（按业务对象组织的端侧入口）
final userRepositoryProvider = Provider<UserRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteUserRepository();
  }
  return MockUserRepository();
});

/// Behavior Repository（行为上报，驱动实时推荐）
final behaviorRepositoryProvider = Provider<BehaviorRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteBehaviorRepository();
  }
  return MockBehaviorRepository();
});

