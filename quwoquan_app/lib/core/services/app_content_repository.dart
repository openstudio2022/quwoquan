import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/data/mock/prototype_mock_data.dart';

enum AppDataSourceMode { mock, remote }

class AppDataSourceModeNotifier extends Notifier<AppDataSourceMode> {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;

  void setMode(AppDataSourceMode mode) {
    state = mode;
  }
}

final appDataSourceModeProvider =
    NotifierProvider<AppDataSourceModeNotifier, AppDataSourceMode>(
  AppDataSourceModeNotifier.new,
);

abstract class AppContentRepository {
  List<Map<String, dynamic>> get discoveryMomentData;
  List<Map<String, dynamic>> get discoveryPhotoData;
  List<Map<String, dynamic>> get discoveryArticleData;
  List<Map<String, dynamic>> get discoveryVideoData;
  Map<String, dynamic>? articleById(String id);

  Map<String, Map<String, dynamic>> get circlesCategoryConfig;
  List<Map<String, dynamic>> get circlesMockCircles;
  List<Map<String, dynamic>> get circlesMockActivities;
  Map<String, dynamic> get circlePageCircleInfo;

  List<Map<String, dynamic>> get chatMockConversations;
  List<Map<String, dynamic>> get chatMockConversationsAtMe;
  List<Map<String, dynamic>> get chatEncryptedConversations;
  Map<String, dynamic> get chatAssistantConversation;
  List<Map<String, dynamic>> get chatMockContactCircles;
  List<Map<String, dynamic>> get chatMockContacts;
  List<Map<String, dynamic>> get chatMockContactGroups;
  List<Map<String, dynamic>> chatMessagesFor(String conversationId);

  List<Map<String, dynamic>> get assistantMemoryData;
  List<Map<String, dynamic>> get assistantTasksData;
  List<Map<String, dynamic>> get assistantSkillsData;
}

class MockAppContentRepository implements AppContentRepository {
  @override
  List<Map<String, dynamic>> get discoveryMomentData =>
      PrototypeMockData.discoveryMomentData;

  @override
  List<Map<String, dynamic>> get discoveryPhotoData =>
      PrototypeMockData.discoveryPhotoData;

  @override
  List<Map<String, dynamic>> get discoveryArticleData =>
      PrototypeMockData.discoveryArticleData;

  @override
  List<Map<String, dynamic>> get discoveryVideoData =>
      PrototypeMockData.discoveryVideoData;

  @override
  Map<String, dynamic>? articleById(String id) => PrototypeMockData.articleById(id);

  @override
  Map<String, Map<String, dynamic>> get circlesCategoryConfig =>
      PrototypeMockData.circlesCategoryConfig;

  @override
  List<Map<String, dynamic>> get circlesMockCircles =>
      PrototypeMockData.circlesMockCircles;

  @override
  List<Map<String, dynamic>> get circlesMockActivities =>
      PrototypeMockData.circlesMockActivities;

  @override
  Map<String, dynamic> get circlePageCircleInfo =>
      PrototypeMockData.circlePageCircleInfo;

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
}

class RemoteAppContentRepository implements AppContentRepository {
  RemoteAppContentRepository();
  final MockAppContentRepository _fallback = MockAppContentRepository();

  @override
  List<Map<String, dynamic>> get discoveryMomentData => _fallback.discoveryMomentData;
  @override
  List<Map<String, dynamic>> get discoveryPhotoData => _fallback.discoveryPhotoData;
  @override
  List<Map<String, dynamic>> get discoveryArticleData => _fallback.discoveryArticleData;
  @override
  List<Map<String, dynamic>> get discoveryVideoData => _fallback.discoveryVideoData;
  @override
  Map<String, dynamic>? articleById(String id) => _fallback.articleById(id);
  @override
  Map<String, Map<String, dynamic>> get circlesCategoryConfig =>
      _fallback.circlesCategoryConfig;
  @override
  List<Map<String, dynamic>> get circlesMockCircles => _fallback.circlesMockCircles;
  @override
  List<Map<String, dynamic>> get circlesMockActivities =>
      _fallback.circlesMockActivities;
  @override
  Map<String, dynamic> get circlePageCircleInfo => _fallback.circlePageCircleInfo;
  @override
  List<Map<String, dynamic>> get chatMockConversations => _fallback.chatMockConversations;
  @override
  List<Map<String, dynamic>> get chatMockConversationsAtMe =>
      _fallback.chatMockConversationsAtMe;
  @override
  List<Map<String, dynamic>> get chatEncryptedConversations =>
      _fallback.chatEncryptedConversations;
  @override
  Map<String, dynamic> get chatAssistantConversation =>
      _fallback.chatAssistantConversation;
  @override
  List<Map<String, dynamic>> get chatMockContactCircles =>
      _fallback.chatMockContactCircles;
  @override
  List<Map<String, dynamic>> get chatMockContacts => _fallback.chatMockContacts;
  @override
  List<Map<String, dynamic>> get chatMockContactGroups =>
      _fallback.chatMockContactGroups;
  @override
  List<Map<String, dynamic>> chatMessagesFor(String conversationId) =>
      _fallback.chatMessagesFor(conversationId);
  @override
  List<Map<String, dynamic>> get assistantMemoryData => _fallback.assistantMemoryData;
  @override
  List<Map<String, dynamic>> get assistantTasksData => _fallback.assistantTasksData;
  @override
  List<Map<String, dynamic>> get assistantSkillsData => _fallback.assistantSkillsData;
}

final appContentRepositoryProvider = Provider<AppContentRepository>((ref) {
  final mode = ref.watch(appDataSourceModeProvider);
  if (mode == AppDataSourceMode.remote) {
    return RemoteAppContentRepository();
  }
  return MockAppContentRepository();
});
