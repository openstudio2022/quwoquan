import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_inbox_dto.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/utils/chat_time_formatter.dart';

class ChatListItemViewModel {
  const ChatListItemViewModel({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.timeLabel,
    required this.avatarUrl,
    required this.avatarCompositeUrls,
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
  final String avatarUrl;
  final List<String> avatarCompositeUrls;
  final IconData? previewIcon;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool isGroup;
  final bool isMuted;
  final bool isPinned;

  bool get hasUnread => unreadCount > 0;
  bool get hasMention => mentionUnreadCount > 0;

  factory ChatListItemViewModel.fromDto(ChatInboxDto dto) {
    final preview = _resolvePreview(
      dto.lastMessageType,
      dto.lastMessagePreview,
    );
    return ChatListItemViewModel(
      id: dto.id,
      title: dto.title.trim().isEmpty
          ? UITextConstants.untitledConversation
          : dto.title.trim(),
      subtitle: preview.text,
      timeLabel: dto.lastMessageTime == null
          ? ''
          : ChatTimeFormatter.formatForConversationList(dto.lastMessageTime!),
      avatarUrl: dto.avatarUrl,
      avatarCompositeUrls: dto.avatarCompositeUrls,
      previewIcon: preview.icon,
      unreadCount: dto.unreadCount,
      mentionUnreadCount: dto.mentionUnreadCount,
      isGroup: dto.type == 'group',
      isMuted: dto.muted,
      isPinned: dto.pinned,
    );
  }

  static _ResolvedPreview _resolvePreview(String type, String preview) {
    final normalized = type.trim().toLowerCase();
    switch (normalized) {
      case 'image':
      case 'photo':
        return _ResolvedPreview(
          icon: CupertinoIcons.photo_fill_on_rectangle_fill,
          text: preview.trim().isEmpty
              ? UITextConstants.chatPreviewImage
              : preview.trim(),
        );
      case 'video':
        return _ResolvedPreview(
          icon: CupertinoIcons.videocam_fill,
          text: preview.trim().isEmpty
              ? UITextConstants.chatPreviewVideo
              : preview.trim(),
        );
      case 'voice':
      case 'audio':
        return _ResolvedPreview(
          icon: CupertinoIcons.mic_fill,
          text: preview.trim().isEmpty
              ? UITextConstants.chatPreviewVoice
              : preview.trim(),
        );
      case 'call':
      case 'phone':
        return _ResolvedPreview(
          icon: CupertinoIcons.phone_fill,
          text: preview.trim().isEmpty
              ? UITextConstants.chatPreviewCall
              : preview.trim(),
        );
      case 'card':
        return _ResolvedPreview(
          icon: CupertinoIcons.person_crop_rectangle_fill,
          text: preview.trim().isEmpty
              ? UITextConstants.chatPreviewCard
              : preview.trim(),
        );
      case 'recalled':
      case 'recall':
        return const _ResolvedPreview(
          icon: null,
          text: UITextConstants.chatPreviewRecalled,
        );
      case 'text':
      default:
        return _ResolvedPreview(icon: null, text: preview.trim());
    }
  }
}

class _ResolvedPreview {
  const _ResolvedPreview({required this.icon, required this.text});

  final IconData? icon;
  final String text;
}
