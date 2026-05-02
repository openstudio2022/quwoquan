import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/contract_fixture_runtime_loader.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/core/models/app_content_prototype_models.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_prototype_codec.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// Mock 实现：canonical 数据来自 content / prototype mock，仅用于 `AppDataSourceMode.mock`。
class MockAppContentRepository implements AppContentRepository {
  static final AppContentPrototypeBundle _p =
      AppContentPrototypeBundle.instance;
  static final List<FeedItemDto>? _contractFeedItems = _loadContractFeedItems();

  @override
  List<FeedItemDto> get discoveryMomentData =>
      _feedItemsByType('micro', ContentMockData.discoveryMomentData);

  @override
  List<FeedItemDto> get discoveryPhotoData =>
      _feedItemsByType('image', ContentMockData.discoveryPhotoData);

  @override
  List<FeedItemDto> get discoveryArticleData =>
      _feedItemsByType('article', ContentMockData.discoveryArticleData);

  @override
  List<FeedItemDto> get discoveryVideoData =>
      _feedItemsByType('video', ContentMockData.discoveryVideoData);

  @override
  Map<String, dynamic>? articleById(String id) {
    final contractItems = _contractFeedItems;
    if (contractItems != null) {
      for (final item in contractItems) {
        if (item.id == id && item.type == 'article') {
          return item.toMap();
        }
      }
    }
    return ContentMockData.articleWireByPostId(id);
  }

  @override
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId) =>
      lookupDiscoveryFeedWireRow(this, postId);

  @override
  List<ChatInboxDto> get chatMockConversations => _p.chatMockConversations;

  @override
  List<ChatInboxDto> get chatMockConversationsAtMe =>
      _p.chatMockConversationsAtMe;

  @override
  List<ChatInboxDto> get chatEncryptedConversations =>
      _p.chatEncryptedConversations;

  @override
  ChatInboxDto get chatAssistantConversation => _p.chatAssistantConversation;

  @override
  List<ChatContactTabCircleRowDto> get chatMockContactCircles =>
      _p.chatMockContactCircles;

  @override
  List<ChatContactRowDto> get chatMockContacts => _p.chatMockContacts;

  @override
  List<ChatContactTabFunGroupRowDto> get chatMockContactGroups =>
      _p.chatMockContactGroups;

  @override
  List<ChatMessageDto> chatMessagesFor(String conversationId) =>
      _p.chatMessagesFor(conversationId);

  @override
  List<AssistantPrototypeMemoryRow> get assistantMemoryData =>
      _p.assistantMemoryData;

  @override
  List<AssistantPrototypeTaskRow> get assistantTasksData =>
      _p.assistantTasksData;

  @override
  List<AssistantPrototypeSkillRow> get assistantSkillsData =>
      _p.assistantSkillsData;

  @override
  HelperReadSummaryPrototype get helperReadSummary => _p.helperReadSummary;

  @override
  CirclePagePrototypeInfo get circlePageCircleInfo => _p.circlePageCircleInfo;

  @override
  Map<String, CircleCategoryTabConfigDto> get circlesCategoryConfig =>
      _p.circlesCategoryConfig;

  @override
  List<CircleActivityPrototypeRow> get circlesMockActivities =>
      _p.circlesMockActivities;

  @override
  List<CircleDto> get circlesMockCircles => _p.circlesMockCircles;

  static List<FeedItemDto>? _loadContractFeedItems() {
    final seed = ContractFixtureRuntimeLoader.contentSeedSet();
    final posts = seed?['posts'];
    if (posts is! List) {
      return null;
    }
    return posts
        .whereType<Map>()
        .map((item) => FeedItemDto.fromMap(item.cast<String, dynamic>()))
        .toList(growable: false);
  }

  static List<FeedItemDto> _feedItemsByType(
    String type,
    List<FeedItemDto> fallback,
  ) {
    final byId = <String, FeedItemDto>{};
    final contractItems = _contractFeedItems
        ?.where((item) => item.type == type)
        .toList(growable: false);
    for (final item in contractItems ?? const <FeedItemDto>[]) {
      byId[item.id] = item;
    }
    for (final item in fallback) {
      byId.putIfAbsent(item.id, () => item);
    }
    return byId.values.toList(growable: false);
  }
}
