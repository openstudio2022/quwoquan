import 'package:quwoquan_app/cloud/services/chat/chat_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

const String _defaultConversationAvatarUrl = '';
const int _defaultGroupAvatarVersion = 0;
const String _defaultLastMessagePreview = '';
const MessageType _defaultLastMessageType = MessageType.text;
const int _defaultLastSequence = 0;
const int _defaultUnreadCount = 0;
const int _defaultMentionUnreadCount = 0;
const bool _defaultMuted = false;
const bool _defaultPinned = false;
const String _defaultCircleId = '';

ChatInboxViewData chatInboxFixture({
  required String id,
  required String type,
  required String title,
  String avatarUrl = _defaultConversationAvatarUrl,
  int groupAvatarVersion = _defaultGroupAvatarVersion,
  String lastMessagePreview = _defaultLastMessagePreview,
  MessageType lastMessageType = _defaultLastMessageType,
  DateTime? lastMessageTime,
  int lastSeq = _defaultLastSequence,
  int unreadCount = _defaultUnreadCount,
  int mentionUnreadCount = _defaultMentionUnreadCount,
  bool muted = _defaultMuted,
  bool pinned = _defaultPinned,
  String circleId = _defaultCircleId,
}) {
  return ChatInboxViewData(
    id: id,
    type: type,
    title: title,
    avatarUrl: avatarUrl,
    groupAvatarVersion: groupAvatarVersion,
    lastMessagePreview: lastMessagePreview,
    lastMessageType: lastMessageType,
    lastMessageTime: lastMessageTime,
    lastSeq: lastSeq,
    unreadCount: unreadCount,
    mentionUnreadCount: mentionUnreadCount,
    muted: muted,
    pinned: pinned,
    circleId: circleId,
  );
}
