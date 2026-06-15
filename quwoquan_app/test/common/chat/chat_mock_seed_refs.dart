import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart'
    as chat_mock_data;

const _chatCurrentUserProfileId =
    chat_mock_data.ChatMockData.currentUserProfileId;
final _chatDisplayNameFor = chat_mock_data.ChatMockData.nameFor;
final _chatAvatarUrlFor = chat_mock_data.ChatMockData.avatarFor;
final _chatConversations = chat_mock_data.ChatMockData.conversations;

String chatCurrentUserProfileId() => _chatCurrentUserProfileId;

String chatDisplayNameFor(String userId) => _chatDisplayNameFor(userId);

String chatAvatarUrlFor(String userId) => _chatAvatarUrlFor(userId);

Map<String, dynamic> chatConversationSeedById(String conversationId) =>
    Map<String, dynamic>.from(
      _chatConversations.firstWhere((item) => item['id'] == conversationId),
    );
