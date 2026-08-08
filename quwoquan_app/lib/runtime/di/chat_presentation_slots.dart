import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/conversation_avatar.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/presentation/customizable_chat_input_bar.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/presentation/voice_message_bubble.dart';

/// Conversation-owned avatar renderer exposed only through the composition
/// root, so Search and Inbox do not import private Chat presentation code.
typedef ConversationAvatarBuilder =
    Widget Function({
      Key? key,
      required String conversationId,
      required String conversationType,
      required String title,
      required String avatarUrl,
      required double size,
      int groupAvatarVersion,
      Color? backgroundColor,
      double? borderRadius,
      IconData groupFallbackIcon,
      IconData directFallbackIcon,
    });

final conversationAvatarBuilderProvider = Provider<ConversationAvatarBuilder>((
  ref,
) {
  return ({
    key,
    required conversationId,
    required conversationType,
    required title,
    required avatarUrl,
    required size,
    groupAvatarVersion = 0,
    backgroundColor,
    borderRadius,
    groupFallbackIcon = Icons.group,
    directFallbackIcon = Icons.person,
  }) {
    return ConversationAvatar(
      key: key,
      conversationId: conversationId,
      conversationType: conversationType,
      title: title,
      avatarUrl: avatarUrl,
      size: size,
      groupAvatarVersion: groupAvatarVersion,
      backgroundColor: backgroundColor,
      borderRadius: borderRadius,
      groupFallbackIcon: groupFallbackIcon,
      directFallbackIcon: directFallbackIcon,
    );
  };
});

/// Message-owned voice bubble renderer used by Conversation and Assistant
/// presentation without a private presentation-to-presentation dependency.
typedef VoiceMessageBubbleBuilder =
    Widget Function({
      Key? key,
      required String messageId,
      required String mediaUrl,
      required int durationMs,
      required List<double> waveform,
      required bool isOutgoing,
      bool isRead,
      String messageStatus,
    });

final voiceMessageBubbleBuilderProvider = Provider<VoiceMessageBubbleBuilder>((
  ref,
) {
  return ({
    key,
    required messageId,
    required mediaUrl,
    required durationMs,
    required waveform,
    required isOutgoing,
    isRead = true,
    messageStatus = 'sent',
  }) {
    return VoiceMessageBubble(
      key: key,
      messageId: messageId,
      mediaUrl: mediaUrl,
      durationMs: durationMs,
      waveform: waveform,
      isOutgoing: isOutgoing,
      isRead: isRead,
      messageStatus: messageStatus,
    );
  };
});

/// Assistant consumes only the text-composer capability. Chat keeps the full
/// attachment/voice model private to the Conversation presentation owner.
typedef AssistantChatInputBuilder =
    Widget Function({
      Key? key,
      TextEditingController? controller,
      FocusNode? focusNode,
      Key? textFieldKey,
      String? hintText,
      int maxTextLength,
      int maxVisibleLines,
      required Future<void> Function(String text) onSend,
      Key? sendButtonKey,
      bool showEmojiButton,
    });

final assistantChatInputBuilderProvider = Provider<AssistantChatInputBuilder>((
  ref,
) {
  return ({
    key,
    controller,
    focusNode,
    textFieldKey,
    hintText,
    maxTextLength = 5000,
    maxVisibleLines = 5,
    required onSend,
    sendButtonKey,
    showEmojiButton = false,
  }) {
    return CustomizableChatInputBar(
      key: key,
      controller: controller,
      focusNode: focusNode,
      textFieldKey: textFieldKey,
      hintText: hintText,
      maxTextLength: maxTextLength,
      maxVisibleLines: maxVisibleLines,
      onSend: (payload) => onSend(payload.text),
      sendButtonKey: sendButtonKey,
      showEmojiButton: showEmojiButton,
    );
  };
});
