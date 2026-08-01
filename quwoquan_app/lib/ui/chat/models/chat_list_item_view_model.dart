import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/message_home_row_dto.g.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class ChatListItemViewModel {
  const ChatListItemViewModel({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.timeLabel,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.previewIcon,
    required this.unreadCount,
    required this.mentionUnreadCount,
    required this.isGroup,
    required this.isMuted,
    required this.isPinned,
  });

  final String id;
  final String title;
  final String subtitle;
  final String timeLabel;

  /// 会话级主头像：单聊优先对方头像；群聊只消费服务端预合成头像。
  final String avatarUrl;
  final int groupAvatarVersion;
  final IconData? previewIcon;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool isGroup;
  final bool isMuted;
  final bool isPinned;

  bool get hasUnread => unreadCount > 0;
  bool get hasMention => mentionUnreadCount > 0;
  bool get isNotification => id.startsWith('notification:');

  factory ChatListItemViewModel.fromDto(
    ChatInboxDto dto, {
    MediaEndpointConfig? mediaEndpointConfig,
  }) {
    final preview = _resolvePreview(
      dto.lastMessageType,
      dto.lastMessagePreview,
    );
    return ChatListItemViewModel(
      id: dto.id,
      title: dto.title.trim().isEmpty
          ? ChatText.untitledConversation
          : dto.title.trim(),
      subtitle: preview.text,
      timeLabel: dto.lastMessageTime == null
          ? ''
          : ChatTimeFormatter.formatForConversationList(dto.lastMessageTime!),
      avatarUrl: resolveAvatarImageUrl(
        dto.avatarUrl,
        endpointConfig: mediaEndpointConfig,
      ),
      groupAvatarVersion: dto.groupAvatarVersion,
      previewIcon: preview.icon,
      unreadCount: dto.unreadCount,
      mentionUnreadCount: dto.mentionUnreadCount,
      isGroup: dto.type == 'group',
      isMuted: dto.muted,
      isPinned: dto.pinned,
    );
  }

  factory ChatListItemViewModel.fromMessageHomeDto(
    MessageHomeRowDto dto, {
    MediaEndpointConfig? mediaEndpointConfig,
  }) {
    final preview = _resolvePreview(MessageType.text, dto.summary);
    final id = dto.conversationId.trim().isNotEmpty
        ? dto.conversationId.trim()
        : 'notification:${dto.notificationId.trim()}';
    return ChatListItemViewModel(
      id: id,
      title: dto.title.trim().isEmpty
          ? ChatText.untitledConversation
          : dto.title.trim(),
      subtitle: preview.text,
      timeLabel: dto.lastActiveAt == null
          ? ''
          : ChatTimeFormatter.formatForConversationList(dto.lastActiveAt!),
      avatarUrl: resolveAvatarImageUrl(
        dto.avatarUrl,
        endpointConfig: mediaEndpointConfig,
      ),
      groupAvatarVersion: dto.groupAvatarVersion,
      previewIcon: preview.icon,
      unreadCount: dto.unreadCount,
      mentionUnreadCount: dto.mentionUnreadCount,
      isGroup: dto.conversationType == 'group',
      isMuted: dto.muted,
      isPinned: dto.pinned,
    );
  }

  static _ResolvedPreview _resolvePreview(MessageType type, String preview) {
    switch (type) {
      case MessageType.image:
        return _ResolvedPreview(
          icon: CupertinoIcons.photo_fill_on_rectangle_fill,
          text: preview.trim().isEmpty
              ? ChatText.chatPreviewImage
              : preview.trim(),
        );
      case MessageType.video:
        return _ResolvedPreview(
          icon: CupertinoIcons.videocam_fill,
          text: preview.trim().isEmpty
              ? ChatText.chatPreviewVideo
              : preview.trim(),
        );
      case MessageType.audio:
        return _ResolvedPreview(
          icon: CupertinoIcons.mic_fill,
          text: preview.trim().isEmpty
              ? ChatText.chatPreviewVoice
              : preview.trim(),
        );
      case MessageType.file:
        return _ResolvedPreview(
          icon: CupertinoIcons.paperclip,
          text: preview.trim().isEmpty
              ? ChatText.chatPreviewFile
              : preview.trim(),
        );
      case MessageType.systemCallLog:
        return _ResolvedPreview(
          icon: CupertinoIcons.phone_fill,
          text: preview.trim().isEmpty
              ? ChatText.chatPreviewCall
              : preview.trim(),
        );
      case MessageType.card:
        return _ResolvedPreview(
          icon: CupertinoIcons.person_crop_rectangle_fill,
          text: preview.trim().isEmpty
              ? ChatText.chatPreviewCard
              : preview.trim(),
        );
      case MessageType.systemAnnouncement:
        return _ResolvedPreview(
          icon: CupertinoIcons.speaker_2_fill,
          text: preview.trim().isEmpty
              ? ChatText.groupAnnouncement
              : preview.trim(),
        );
      case MessageType.text:
        return _ResolvedPreview(icon: null, text: preview.trim());
    }
  }
}

class _ResolvedPreview {
  const _ResolvedPreview({required this.icon, required this.text});

  final IconData? icon;
  final String text;
}
