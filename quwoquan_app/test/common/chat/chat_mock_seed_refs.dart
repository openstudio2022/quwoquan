import 'package:quwoquan_app/cloud/services/chat/mock/chat_mock_data.dart'
    show ChatMockData;

String chatCurrentUserProfileId() => ChatMockData.currentUserProfileId;

String chatDisplayNameFor(String userId) => ChatMockData.nameFor(userId);

String chatAvatarUrlFor(String userId) => ChatMockData.avatarFor(userId);
