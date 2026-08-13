import 'conversation_state_typed_double.dart';
import 'chat_state_seed_builder.dart';

final _chatFixtureEngine = InMemoryChatStateEngine(
  seed: minimalChatStateSeed(),
);

String chatCurrentUserProfileId() => _chatFixtureEngine.currentUserId;

String chatDisplayNameFor(String userId) =>
    _chatFixtureEngine.displayNameFor(userId);

String chatAvatarUrlFor(String userId) => _chatFixtureEngine.avatarFor(userId);

Map<String, dynamic> chatConversationSeedById(String conversationId) =>
    Map<String, dynamic>.from(
      _chatFixtureEngine.conversationSeedById(conversationId),
    );
