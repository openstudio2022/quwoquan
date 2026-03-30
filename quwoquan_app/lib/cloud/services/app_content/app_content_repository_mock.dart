import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/core/mock/prototype_mock_data.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// Mock 实现：canonical 数据来自 content / prototype mock，仅用于 `AppDataSourceMode.mock`。
class MockAppContentRepository implements AppContentRepository {
  @override
  List<Map<String, dynamic>> get discoveryMomentData =>
      ContentMockData.discoveryMomentData;

  @override
  List<Map<String, dynamic>> get discoveryPhotoData =>
      ContentMockData.discoveryPhotoData;

  @override
  List<Map<String, dynamic>> get discoveryArticleData =>
      ContentMockData.discoveryArticleData;

  @override
  List<Map<String, dynamic>> get discoveryVideoData =>
      ContentMockData.discoveryVideoData;

  @override
  Map<String, dynamic>? articleById(String id) => PrototypeMockData.articleById(id);

  @override
  Map<String, dynamic>? discoveryFeedWireRowByPostId(String postId) =>
      lookupDiscoveryFeedWireRow(this, postId);

  @override
  List<Map<String, dynamic>> get chatMockConversations =>
      PrototypeMockData.chatMockConversations;

  @override
  List<Map<String, dynamic>> get chatMockConversationsAtMe =>
      PrototypeMockData.chatMockConversationsAtMe;

  @override
  List<Map<String, dynamic>> get chatEncryptedConversations =>
      PrototypeMockData.chatEncryptedConversations;

  @override
  Map<String, dynamic> get chatAssistantConversation =>
      PrototypeMockData.chatAssistantConversation;

  @override
  List<Map<String, dynamic>> get chatMockContactCircles =>
      PrototypeMockData.chatMockContactCircles;

  @override
  List<Map<String, dynamic>> get chatMockContacts =>
      PrototypeMockData.chatMockContacts;

  @override
  List<Map<String, dynamic>> get chatMockContactGroups =>
      PrototypeMockData.chatMockContactGroups;

  @override
  List<Map<String, dynamic>> chatMessagesFor(String conversationId) =>
      PrototypeMockData.chatMessagesFor(conversationId);

  @override
  List<Map<String, dynamic>> get assistantMemoryData =>
      PrototypeMockData.assistantMemoryData;

  @override
  List<Map<String, dynamic>> get assistantTasksData =>
      PrototypeMockData.assistantTasksData;

  @override
  List<Map<String, dynamic>> get assistantSkillsData =>
      PrototypeMockData.assistantSkillsData;

  @override
  Map<String, dynamic> get helperReadSummary =>
      PrototypeMockData.helperReadSummary;

  @override
  Map<String, dynamic> get circlePageCircleInfo =>
      PrototypeMockData.circlePageCircleInfo;

  @override
  Map<String, Map<String, dynamic>> get circlesCategoryConfig =>
      PrototypeMockData.circlesCategoryConfig;

  @override
  List<Map<String, dynamic>> get circlesMockActivities =>
      PrototypeMockData.circlesMockActivities;

  @override
  List<Map<String, dynamic>> get circlesMockCircles =>
      PrototypeMockData.circlesMockCircles;
}
