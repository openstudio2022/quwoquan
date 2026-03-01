import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_interaction_repository.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/report_repository.dart';
import 'package:quwoquan_app/cloud/services/user/block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/keyword_block_repository.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
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

/// 用户数据Provider
class UserDataNotifier extends Notifier<User?> {
  @override
  User? build() {
    return null;
  }

  Future<void> loadUser(String username) async {
    state = _mockUserData[username] ??
        User(
          id: username,
          username: username,
        );
  }

  static final Map<String, User> _mockUserData = {
    'nature_photographer': User(
      id: 'nature_photographer',
      username: 'nature_photographer',
      displayName: '自然摄影师',
      avatar: 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1501785888041-af3ef285b470?w=1200',
    ),
    'travel_photographer': User(
      id: 'travel_photographer',
      username: 'travel_photographer',
      displayName: '旅行摄影师',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1539635278303-d4002c07eae3?w=1200',
    ),
    'street_photo': User(
      id: 'street_photo',
      username: 'street_photo',
      displayName: '街头摄影',
      avatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=1200',
    ),
    'a1': User(
      id: 'a1',
      username: 'a1',
      displayName: '楹语小筑',
      avatar: 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?w=1200',
    ),
    'a2': User(
      id: 'a2',
      username: 'a2',
      displayName: '自然摄影师',
      avatar: 'https://images.unsplash.com/photo-1534067783941-51c9c23ecefd?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1440342359743-84fcb8c21f21?w=1200',
    ),
    'a3': User(
      id: 'a3',
      username: 'a3',
      displayName: '未来科技',
      avatar: 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200',
    ),
    'u1': User(
      id: 'u1',
      username: 'u1',
      displayName: '你的皮炎有点辣',
      avatar: 'https://images.unsplash.com/photo-1599566150163-29194dcaad36?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=1200',
    ),
    'u2': User(
      id: 'u2',
      username: 'u2',
      displayName: '仅分组可见',
      avatar: 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1432888498266-38ffec3eaf0a?w=1200',
    ),
    'u3': User(
      id: 'u3',
      username: 'u3',
      displayName: '原价帝吧',
      avatar: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200',
    ),
    'u4': User(
      id: 'u4',
      username: 'u4',
      displayName: '李想',
      avatar: 'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1200',
    ),
    'tech_daily': User(
      id: 'tech_daily',
      username: 'tech_daily',
      displayName: 'TechDaily',
      avatar: 'https://images.unsplash.com/photo-1531427186611-ecfd6d936c79?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1518770660439-4636190af475?w=1200',
    ),
    'mo_yun': User(
      id: 'mo_yun',
      username: 'mo_yun',
      displayName: '墨韵',
      avatar: 'https://images.unsplash.com/photo-1545996124-0501eb296251?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=1200',
    ),
    'travel_notes': User(
      id: 'travel_notes',
      username: 'travel_notes',
      displayName: '旅行笔记',
      avatar: 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=100',
      backgroundImage: 'https://images.unsplash.com/photo-1469854523086-cc02fe5d8800?w=1200',
    ),
  };
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

