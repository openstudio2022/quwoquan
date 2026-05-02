import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/discovery_wire_lookup.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/core/models/app_content_prototype_models.dart';

export 'package:quwoquan_app/cloud/services/app_content/app_content_repository_provider.dart';

enum AppDataSourceMode { mock, remote }

class AppDataSourceModeNotifier extends Notifier<AppDataSourceMode> {
  @override
  AppDataSourceMode build() {
    const v = String.fromEnvironment('APP_DATA_SOURCE', defaultValue: '');
    if (v == 'remote') {
      return AppDataSourceMode.remote;
    }
    if (v == 'mock') {
      return AppDataSourceMode.mock;
    }
    if (CloudRuntimeConfig.appRuntimeEnv == 'beta' ||
        CloudRuntimeConfig.appRuntimeEnv == 'gamma') {
      return AppDataSourceMode.remote;
    }
    if (CloudRuntimeConfig.appRuntimeEnv == 'alpha') {
      return AppDataSourceMode.mock;
    }
    return kReleaseMode ? AppDataSourceMode.remote : AppDataSourceMode.mock;
  }

  void setMode(AppDataSourceMode mode) {
    state = mode;
  }
}

final appDataSourceModeProvider =
    NotifierProvider<AppDataSourceModeNotifier, AppDataSourceMode>(
      AppDataSourceModeNotifier.new,
    );

/// 应用级内容相关 mock / 过渡数据入口（含发现区 wire 切片）。
///
/// **强类型发现列表**：遍历四类 mock 为 [PostBaseDto] 时使用
/// [AppContentRepositoryDiscoveryPosts.discoveryPostsAsDtos]（与 `discovery*Data` 同源，跳过不可解析行）。
/// **单条 + 扩展 wire**：[lookupDiscoveryFeedWireRow] / [lookupDiscoveryPostBaseDto]。
///
/// 聊天 / 圈子 / 助理 Tab 原型数据均为 **codegen DTO 或显式原型模型**，不再对外暴露 `List<Map<String,dynamic>>`。
abstract class AppContentRepository {
  @Deprecated(
    '发现区列表请使用 ContentRepository；内嵌目录数据见 ContentMockData（仅组合根/Repository 实现侧）。',
  )
  List<FeedItemDto> get discoveryMomentData;
  @Deprecated(
    '发现区列表请使用 ContentRepository；内嵌目录数据见 ContentMockData（仅组合根/Repository 实现侧）。',
  )
  List<FeedItemDto> get discoveryPhotoData;
  @Deprecated(
    '发现区列表请使用 ContentRepository；内嵌目录数据见 ContentMockData（仅组合根/Repository 实现侧）。',
  )
  List<FeedItemDto> get discoveryArticleData;
  @Deprecated(
    '发现区列表请使用 ContentRepository；内嵌目录数据见 ContentMockData（仅组合根/Repository 实现侧）。',
  )
  List<FeedItemDto> get discoveryVideoData;
  @Deprecated('文章详情请优先 ContentRepository.getPost；Prototype 仅过渡期保留。')
  Map<String, dynamic>? articleById(String id);

  /// 发现 Feed 原型数据中按 postId 定位单行 Map（分享模板圈名/tags 等扩展字段；非 codegen DTO）。
  @Deprecated(
    '请使用 ContentRepository.discoveryPresentationWireForPost；或 lookupCanonicalDiscoveryWireRowByPostId（非 UI）。',
  )
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId);

  List<ChatInboxDto> get chatMockConversations;
  List<ChatInboxDto> get chatMockConversationsAtMe;
  List<ChatInboxDto> get chatEncryptedConversations;
  ChatInboxDto get chatAssistantConversation;
  List<ChatContactTabCircleRowDto> get chatMockContactCircles;
  List<ChatContactTabFunGroupRowDto> get chatMockContactGroups;
  List<ChatContactRowDto> get chatMockContacts;
  List<ChatMessageDto> chatMessagesFor(String conversationId);

  List<AssistantPrototypeMemoryRow> get assistantMemoryData;
  List<AssistantPrototypeTaskRow> get assistantTasksData;
  List<AssistantPrototypeSkillRow> get assistantSkillsData;

  HelperReadSummaryPrototype get helperReadSummary;

  CirclePagePrototypeInfo get circlePageCircleInfo;
  Map<String, CircleCategoryTabConfigDto> get circlesCategoryConfig;
  List<CircleActivityPrototypeRow> get circlesMockActivities;
  List<CircleDto> get circlesMockCircles;
}

/// 在发现区四类 mock 聚合中按帖子 id 查找原始 wire 行（仅 parse/原型边界用）。
Map<String, dynamic>? lookupDiscoveryFeedWireRow(
  AppContentRepository repo,
  String postId,
) {
  return findDiscoveryWireRowByPostId(
    postId,
    aggregateDiscoveryWireSlices(
      photo: repo.discoveryPhotoData,
      video: repo.discoveryVideoData,
      article: repo.discoveryArticleData,
      moment: repo.discoveryMomentData,
    ),
  );
}

/// 在四类发现 mock 聚合中按帖子 id 解析为 [PostBaseDto]（无则 null）。
///
/// 与 [lookupDiscoveryFeedWireRow] 成对使用：优先消费本函数的强类型结果，仅在需要 wire 扩展字段时回退 map。
PostBaseDto? lookupDiscoveryPostBaseDto(
  AppContentRepository repo,
  String postId,
) {
  final row = lookupDiscoveryFeedWireRow(repo, postId);
  if (row == null || row.isEmpty) {
    return null;
  }
  return postBaseDtoFromMap(row);
}

class RemoteAppContentRepository implements AppContentRepository {
  RemoteAppContentRepository();

  static final List<FeedItemDto> _emptyFeed = List<FeedItemDto>.unmodifiable(
    <FeedItemDto>[],
  );

  static final List<ChatInboxDto> _emptyInbox = List<ChatInboxDto>.unmodifiable(
    <ChatInboxDto>[],
  );
  static final List<ChatContactTabCircleRowDto> _emptyCircles =
      List<ChatContactTabCircleRowDto>.unmodifiable(
        <ChatContactTabCircleRowDto>[],
      );
  static final List<ChatContactTabFunGroupRowDto> _emptyGroups =
      List<ChatContactTabFunGroupRowDto>.unmodifiable(
        <ChatContactTabFunGroupRowDto>[],
      );
  static final List<ChatContactRowDto> _emptyContacts =
      List<ChatContactRowDto>.unmodifiable(<ChatContactRowDto>[]);
  static final List<ChatMessageDto> _emptyMessages =
      List<ChatMessageDto>.unmodifiable(<ChatMessageDto>[]);
  static final List<AssistantPrototypeMemoryRow> _emptyMemories =
      List<AssistantPrototypeMemoryRow>.unmodifiable(
        <AssistantPrototypeMemoryRow>[],
      );
  static final List<AssistantPrototypeTaskRow> _emptyTasks =
      List<AssistantPrototypeTaskRow>.unmodifiable(
        <AssistantPrototypeTaskRow>[],
      );
  static final List<AssistantPrototypeSkillRow> _emptySkills =
      List<AssistantPrototypeSkillRow>.unmodifiable(
        <AssistantPrototypeSkillRow>[],
      );
  static final List<CircleActivityPrototypeRow> _emptyActivities =
      List<CircleActivityPrototypeRow>.unmodifiable(
        <CircleActivityPrototypeRow>[],
      );
  static final List<CircleDto> _emptyCircleDtos = List<CircleDto>.unmodifiable(
    <CircleDto>[],
  );

  static final ChatInboxDto _emptyInboxRow = ChatInboxDto();
  static const CirclePagePrototypeInfo _emptyCirclePage =
      CirclePagePrototypeInfo(
        name: '',
        id: '',
        avatar: '',
        cover: '',
        desc: '',
        stats: CirclePrototypeStats(
          members: '',
          groups: '',
          fans: '',
          likes: '',
        ),
        hasNewMessages: false,
      );
  static const HelperReadSummaryPrototype _emptyHelperRead =
      HelperReadSummaryPrototype(oneLiner: '', dimensions: []);

  @override
  List<FeedItemDto> get discoveryMomentData => _emptyFeed;

  @override
  List<FeedItemDto> get discoveryPhotoData => _emptyFeed;

  @override
  List<FeedItemDto> get discoveryArticleData => _emptyFeed;

  @override
  List<FeedItemDto> get discoveryVideoData => _emptyFeed;

  @override
  Map<String, dynamic>? articleById(String id) => null;

  @override
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId) => null;

  @override
  List<ChatInboxDto> get chatMockConversations => _emptyInbox;

  @override
  List<ChatInboxDto> get chatMockConversationsAtMe => _emptyInbox;

  @override
  List<ChatInboxDto> get chatEncryptedConversations => _emptyInbox;

  @override
  ChatInboxDto get chatAssistantConversation => _emptyInboxRow;

  @override
  List<ChatContactTabCircleRowDto> get chatMockContactCircles => _emptyCircles;

  @override
  List<ChatContactTabFunGroupRowDto> get chatMockContactGroups => _emptyGroups;

  @override
  List<ChatContactRowDto> get chatMockContacts => _emptyContacts;

  @override
  List<ChatMessageDto> chatMessagesFor(String conversationId) => _emptyMessages;

  @override
  List<AssistantPrototypeMemoryRow> get assistantMemoryData => _emptyMemories;

  @override
  List<AssistantPrototypeTaskRow> get assistantTasksData => _emptyTasks;

  @override
  List<AssistantPrototypeSkillRow> get assistantSkillsData => _emptySkills;

  @override
  HelperReadSummaryPrototype get helperReadSummary => _emptyHelperRead;

  @override
  CirclePagePrototypeInfo get circlePageCircleInfo => _emptyCirclePage;

  @override
  Map<String, CircleCategoryTabConfigDto> get circlesCategoryConfig => const {
    'all': CircleCategoryTabConfigDto(label: '推荐'),
  };

  @override
  List<CircleActivityPrototypeRow> get circlesMockActivities =>
      _emptyActivities;

  @override
  List<CircleDto> get circlesMockCircles => _emptyCircleDtos;
}

/// 在 [AppContentRepository] 四类 `discovery*Data` wire 列表之上提供强类型视图。
///
/// 与 [lookupDiscoveryPostBaseDto] 同源：逐行 [postBaseDtoFromMap]；不可解析行跳过。
/// 需要扩展 wire 键时仍用 [lookupDiscoveryFeedWireRow]。
extension AppContentRepositoryDiscoveryPosts on AppContentRepository {
  List<PostBaseDto> get discoveryPostsAsDtos {
    final items = <FeedItemDto>[
      ...discoveryPhotoData,
      ...discoveryVideoData,
      ...discoveryArticleData,
      ...discoveryMomentData,
    ];
    final out = <PostBaseDto>[];
    for (final item in items) {
      try {
        out.add(postBaseDtoFromMap(item.toDiscoveryWireMap()));
      } catch (_) {
        continue;
      }
    }
    return out;
  }
}
