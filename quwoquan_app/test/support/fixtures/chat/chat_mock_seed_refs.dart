import 'package:quwoquan_cloud_mock/chat_fixture.dart';

final _chatFixtureEngine = AlphaChatStateEngine();

String chatCurrentUserProfileId() => _chatFixtureEngine.currentUserId;

String chatDisplayNameFor(String userId) =>
    _chatFixtureEngine.displayNameFor(userId);

String chatAvatarUrlFor(String userId) => _chatFixtureEngine.avatarFor(userId);

Map<String, dynamic> chatConversationSeedById(String conversationId) =>
    Map<String, dynamic>.from(
      _chatFixtureEngine.conversationSeedById(conversationId),
    );
