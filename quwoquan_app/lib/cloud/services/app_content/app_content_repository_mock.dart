import 'package:quwoquan_app/cloud/chat/models/chat_contact_tab_row_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_contact_row_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_message_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/core/models/app_content_prototype_models.dart';
import 'package:quwoquan_app/cloud/services/app_content/app_content_prototype_codec.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// Mock 实现：canonical 数据来自 content / prototype mock，仅用于 `AppDataSourceMode.mock`。
class MockAppContentRepository implements AppContentRepository {
  static final AppContentPrototypeBundle _p = AppContentPrototypeBundle.instance;

  @override
  List<FeedItemDto> get discoveryMomentData =>
      ContentMockData.discoveryMomentData;

  @override
  List<FeedItemDto> get discoveryPhotoData =>
      ContentMockData.discoveryPhotoData;

  @override
  List<FeedItemDto> get discoveryArticleData =>
      ContentMockData.discoveryArticleData;

  @override
  List<FeedItemDto> get discoveryVideoData =>
      ContentMockData.discoveryVideoData;

  @override
  Map<String, dynamic>? articleById(String id) =>
      ContentMockData.articleWireByPostId(id);

  @override
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId) =>
      lookupDiscoveryFeedWireRow(this, postId);

  @override
  List<ChatInboxDto> get chatMockConversations => _p.chatMockConversations;

  @override
  List<ChatInboxDto> get chatMockConversationsAtMe => _p.chatMockConversationsAtMe;

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
}
