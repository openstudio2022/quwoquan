import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// Inbox application boundary for the shared conversation cache.
///
/// The conversation object owns the concrete cache. Inbox state only consumes
/// its own typed rows and never imports the concrete adapter or storage record.
///
/// `chat.chat_inbox_view` 是 projection（`access.commands: none`），因此这里只有
/// 一条写入面 [replaceInbox]：安装 inbox projection 的远端读结果快照。本地不得存在
/// 第二真相源，所以没有任何 command port，也没有逐字段改写投影行的写入面。
///
/// 用户可感的即时反馈由 [applyOptimisticInboxHint] 承担：它是**易失的展示提示**，
/// 只叠加在读取时刻，不写入持久缓存，并在下一次 [replaceInbox] 落地时整体丢弃。
/// 判定是否已读、未读数真值一律以 projection 的远端读结果为准。
abstract interface class ChatInboxCache {
  List<ChatInboxCacheEntry> readInbox();

  ChatInboxCacheEntry? readInboxEntry(String conversationId);

  /// 安装 inbox projection 的远端读结果快照，并丢弃全部乐观提示。
  void replaceInbox(Iterable<ChatInboxCacheEntry> items);

  /// 叠加一条易失的乐观展示提示（本地乐观清零未读、WS 到达后的预览与角标）。
  ///
  /// 实现必须只改内存叠加层：不得写持久缓存，不得让提示在进程重启后存活，也不得
  /// 让提示覆盖比它更新的 projection 读结果。
  void applyOptimisticInboxHint(
    String conversationId,
    ChatInboxOptimisticHint hint,
  );

  void removeInbox(String conversationId);

  void addInboxListener(void Function() listener);

  void removeInboxListener(void Function() listener);
}

final class ChatInboxCacheEntry {
  const ChatInboxCacheEntry({
    required this.id,
    required this.type,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.lastMessagePreview,
    required this.lastMessageType,
    required this.lastMessageTime,
    required this.lastSeq,
    required this.unreadCount,
    required this.mentionUnreadCount,
    required this.muted,
    required this.pinned,
    required this.circleId,
  });

  final String id;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String lastMessagePreview;
  final MessageType lastMessageType;
  final DateTime? lastMessageTime;
  final int lastSeq;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final String circleId;
}

/// 易失的 inbox 展示提示：只影响读取时刻的呈现，不进入持久缓存，也不是未读真值。
final class ChatInboxOptimisticHint {
  const ChatInboxOptimisticHint({
    this.lastMessagePreview,
    this.lastMessageAt,
    this.unreadCount,
    this.mentionUnreadCount,
  });

  final String? lastMessagePreview;
  final DateTime? lastMessageAt;
  final int? unreadCount;
  final int? mentionUnreadCount;

  ChatInboxCacheEntry applyTo(ChatInboxCacheEntry entry) {
    return ChatInboxCacheEntry(
      id: entry.id,
      type: entry.type,
      title: entry.title,
      avatarUrl: entry.avatarUrl,
      groupAvatarVersion: entry.groupAvatarVersion,
      lastMessagePreview: lastMessagePreview ?? entry.lastMessagePreview,
      lastMessageType: entry.lastMessageType,
      lastMessageTime: lastMessageAt ?? entry.lastMessageTime,
      lastSeq: entry.lastSeq,
      unreadCount: unreadCount ?? entry.unreadCount,
      mentionUnreadCount: mentionUnreadCount ?? entry.mentionUnreadCount,
      muted: entry.muted,
      pinned: entry.pinned,
      circleId: entry.circleId,
    );
  }
}
