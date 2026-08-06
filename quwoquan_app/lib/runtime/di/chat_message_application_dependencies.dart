import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_message_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/chat_send_outbox.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/message_home_rows_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/voice_player_manager.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/voice_send_provider.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_message_timeline.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/chat_send_outbox_control.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_rows.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/voice_message_interaction.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';

/// Reactive read model exported by runtime composition. The Message notifier
/// itself remains object-private.
final chatMessageTimelineProvider =
    Provider.family<ChatMessageTimelineSnapshot, String>((ref, conversationId) {
      return ref.watch(chatMessageProvider(conversationId)).toPublicSnapshot();
    });

/// Narrow command surface exported by runtime composition.
final chatMessageTimelineControllerProvider =
    Provider.family<ChatMessageTimelineController, String>((
      ref,
      conversationId,
    ) {
      return ref.watch(chatMessageProvider(conversationId).notifier);
    });

final chatVoiceSendStateProvider = Provider.family<VoiceSendState, String>((
  ref,
  conversationId,
) {
  return ref.watch(voiceSendProvider(conversationId));
});

final chatVoiceSendControllerProvider =
    Provider.family<VoiceSendController, String>((ref, conversationId) {
      return ref.watch(voiceSendProvider(conversationId).notifier);
    });

final chatVoicePlaybackControlProvider = Provider<VoicePlaybackControl>((ref) {
  return ref.watch(voicePlayerManagerProvider.notifier);
});

final messageHomeRowsProvider =
    FutureProvider.family<MessageHomeRowsSnapshot, String>((ref, filter) {
      return ref.watch(messageHomeRowsStateProvider(filter).future);
    });

final messageHomeRowsRefreshProvider = Provider.family<void Function(), String>(
  (ref, filter) =>
      () => ref.invalidate(messageHomeRowsStateProvider(filter)),
);

void refreshMessageHomeRows(WidgetRef ref, String filter) {
  ref.read(messageHomeRowsRefreshProvider(filter))();
}

void refreshConversationMessageReadState(WidgetRef ref, String conversationId) {
  ref.read(chatInboxListCommandsProvider).markConversationRead(conversationId);
  for (final filter in messageHomeFilters) {
    ref.invalidate(messageHomeRowsStateProvider(filter));
  }
}

final chatSendOutboxQueueLengthProvider = Provider<int>((ref) {
  return ref.watch(chatSendOutboxProvider);
});

final chatSendOutboxControlProvider = Provider<ChatSendOutboxControl>((ref) {
  return ref.watch(chatSendOutboxProvider.notifier);
});

void resetChatSendOutbox(Ref ref) {
  ref.invalidate(chatSendOutboxProvider);
}
