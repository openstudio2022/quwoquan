import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/media/media_download_cache.dart';
import 'package:quwoquan_app/cloud/media/media_upload_manager.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/circle/circle_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_interaction_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/report_repository.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/keyword_block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_profile_repository.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/services/data_service.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/core/services/visit_recorder_service.dart';
import 'package:quwoquan_app/core/models/user_models.dart';

/// 主题相关的便捷Provider
final isDarkProvider = Provider<bool>((ref) {
  return ref.watch(themeProvider).isDark;
});

/// 从小趣对话返回时恢复的 tab 索引（0=发现 1=圈子 3=趣聊 4=我的）
/// 由底部栏 C 位进入小趣时写入，返回时读取并跳转
final lastMainTabBeforeAssistantProvider =
    NotifierProvider<LastMainTabBeforeAssistantNotifier, int?>(
  LastMainTabBeforeAssistantNotifier.new,
);

class LastMainTabBeforeAssistantNotifier extends Notifier<int?> {
  @override
  int? build() => null;

  void set(int? value) => state = value;
}

/// 用户数据Provider — 通过 UserProfileRepository 加载档案
class UserDataNotifier extends Notifier<User?> {
  @override
  User? build() {
    return null;
  }

  Future<void> loadUser(String userId) async {
    try {
      final repo = ref.read(userProfileRepositoryProvider);
      final profile = await repo.getUserProfile(userId);
      state = User(
        id: profile['userId']?.toString() ?? userId,
        username: userId,
        displayName: profile['nickname']?.toString(),
        avatarUrl: profile['avatarUrl']?.toString(),
        bio: profile['bio']?.toString(),
        backgroundImage: profile['backgroundUrl']?.toString(),
      );
    } catch (_) {
      state = User(id: userId, username: userId);
    }
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
      final dtos = await _contentRepository.listDiscoveryFeed(
        category: category,
        subCategory: subCategory,
        cursor: cursor,
        limit: limit ?? GeneratedPostRuntimeMetadata.feedDefaultLimit,
      );
      final remoteItems = dtos.map((dto) => dto.toMap()).toList(growable: false);
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
  return MockChatRepository();
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

/// UserProfile Repository（用户主页：帖子 / 作品集 / 生活记录）
final userProfileRepositoryProvider = Provider<UserProfileRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteUserProfileRepository()
      : const MockUserProfileRepository();
});

/// ContentInteraction Repository（like/unlike/favorite/unfavorite）
final contentInteractionRepositoryProvider = Provider<ContentInteractionRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteContentInteractionRepository()
      : MockContentInteractionRepository();
});

/// Block Repository（拉黑/取消拉黑用户）
final blockRepositoryProvider = Provider<BlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteBlockRepository()
      : MockBlockRepository();
});

/// Report Repository（内容举报）
final reportRepositoryProvider = Provider<ReportRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteReportRepository()
      : MockReportRepository();
});

/// KeywordBlock Repository（屏蔽词设置）
final keywordBlockRepositoryProvider = Provider<KeywordBlockRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteKeywordBlockRepository()
      : MockKeywordBlockRepository();
});

/// Circle Repository（圈子管理、成员、存储、Feed）
final circleRepositoryProvider = Provider<CircleRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteCircleRepository()
      : MockCircleRepository();
});

/// RTC Repository（实时通话：发起、接听、挂断、录制等）
final rtcRepositoryProvider = Provider<RtcRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  return mode == AppDataSourceMode.remote
      ? RemoteRtcRepository()
      : MockRtcRepository();
});

/// Media Upload Manager（统一媒体上传队列 + 并发 + 重试 + 离线恢复）
final mediaUploadManagerProvider = Provider<MediaUploadManager>((ref) {
  final manager = MediaUploadManager();
  manager.startOfflineMonitor();
  ref.onDispose(manager.dispose);
  return manager;
});

/// Media Download Cache（LRU 媒体下载缓存，默认 200MB）
final mediaDownloadCacheProvider = Provider<MediaDownloadCache>((ref) {
  return MediaDownloadCache();
});

