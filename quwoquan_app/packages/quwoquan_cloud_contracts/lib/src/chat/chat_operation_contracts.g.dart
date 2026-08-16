// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 3ecf7598e8529139019cc3bead6cbaf73599a7afae10f147a1dda961cfcaf4da

library;

import '../operation_request_payload.dart';
import "../generated/shared_operation_enums.g.dart";
import "../generated/shared_operation_types.g.dart";

export "../generated/shared_operation_enums.g.dart";
export "../generated/shared_operation_types.g.dart";

part '../generated/requests/chat/chat_operation_contracts.g.requests.g.dart';

enum ChatContactSource {
  conversation("conversation"),
  mutual("mutual"),
  following("following"),
  contactDiscovery("contact_discovery"),
  circle("circle"),
  group("group");

  const ChatContactSource(this.wireName);

  final String wireName;

  static ChatContactSource fromWire(Object? value, String path) {
    return switch (value) {
      "conversation" => ChatContactSource.conversation,
      "mutual" => ChatContactSource.mutual,
      "following" => ChatContactSource.following,
      "contact_discovery" => ChatContactSource.contactDiscovery,
      "circle" => ChatContactSource.circle,
      "group" => ChatContactSource.group,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConversationAccessMode {
  active("active"),
  readOnly("read_only");

  const ConversationAccessMode(this.wireName);

  final String wireName;

  static ConversationAccessMode fromWire(Object? value, String path) {
    return switch (value) {
      "active" => ConversationAccessMode.active,
      "read_only" => ConversationAccessMode.readOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ConversationPostingPolicy {
  memberChat("member_chat"),
  announcementsOnly("announcements_only");

  const ConversationPostingPolicy(this.wireName);

  final String wireName;

  static ConversationPostingPolicy fromWire(Object? value, String path) {
    return switch (value) {
      "member_chat" => ConversationPostingPolicy.memberChat,
      "announcements_only" => ConversationPostingPolicy.announcementsOnly,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MemberListSort {
  joinedAsc("joined_asc"),
  displayNameAsc("display_name_asc");

  const MemberListSort(this.wireName);

  final String wireName;

  static MemberListSort fromWire(Object? value, String path) {
    return switch (value) {
      "joined_asc" => MemberListSort.joinedAsc,
      "display_name_asc" => MemberListSort.displayNameAsc,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MessageCardKind {
  profileQr("profile_qr"),
  contentPost("content_post"),
  userProfile("user_profile"),
  entityProfile("entity_profile"),
  circle("circle"),
  gathering("gathering"),
  rtcCallLog("rtc_call_log"),
  intersectionIcebreaker("intersection_icebreaker");

  const MessageCardKind(this.wireName);

  final String wireName;

  static MessageCardKind fromWire(Object? value, String path) {
    return switch (value) {
      "profile_qr" => MessageCardKind.profileQr,
      "content_post" => MessageCardKind.contentPost,
      "user_profile" => MessageCardKind.userProfile,
      "entity_profile" => MessageCardKind.entityProfile,
      "circle" => MessageCardKind.circle,
      "gathering" => MessageCardKind.gathering,
      "rtc_call_log" => MessageCardKind.rtcCallLog,
      "intersection_icebreaker" => MessageCardKind.intersectionIcebreaker,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MessageStatus {
  sent("sent"),
  recalled("recalled");

  const MessageStatus(this.wireName);

  final String wireName;

  static MessageStatus fromWire(Object? value, String path) {
    return switch (value) {
      "sent" => MessageStatus.sent,
      "recalled" => MessageStatus.recalled,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum MessageType {
  text("text"),
  image("image"),
  video("video"),
  audio("audio"),
  file("file"),
  card("card"),
  systemCallLog("system_call_log"),
  systemAnnouncement("system_announcement");

  const MessageType(this.wireName);

  final String wireName;

  static MessageType fromWire(Object? value, String path) {
    return switch (value) {
      "text" => MessageType.text,
      "image" => MessageType.image,
      "video" => MessageType.video,
      "audio" => MessageType.audio,
      "file" => MessageType.file,
      "card" => MessageType.card,
      "system_call_log" => MessageType.systemCallLog,
      "system_announcement" => MessageType.systemAnnouncement,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum SelectableGroupConversationSource {
  group("group"),
  circle("circle");

  const SelectableGroupConversationSource(this.wireName);

  final String wireName;

  static SelectableGroupConversationSource fromWire(Object? value, String path) {
    return switch (value) {
      "group" => SelectableGroupConversationSource.group,
      "circle" => SelectableGroupConversationSource.circle,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class ChatContactListRow {
  const ChatContactListRow({
    required this.userId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.bio,
    required this.metFrom,
    required this.lastInteraction,
    required this.relationState,
    required this.conversationId,
    required this.conversationType,
    required this.subtitle,
    required this.highlightText,
    required this.matchedField,
    required this.source,
    required this.isStarred,
  });

  final String userId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String bio;
  final String metFrom;
  final String lastInteraction;
  final String relationState;
  final String conversationId;
  final String conversationType;
  final String subtitle;
  final String highlightText;
  final String matchedField;
  final String source;
  final bool isStarred;

  factory ChatContactListRow.fromWire(Map<String, Object?> map, [String path = "ChatContactListRow"]) {
    _rejectUnknownFields(map, const <String>{"userId", "userHandle", "displayName", "avatarUrl", "bio", "metFrom", "lastInteraction", "relationState", "conversationId", "conversationType", "subtitle", "highlightText", "matchedField", "source", "isStarred"}, path);
    return ChatContactListRow(
      userId: _requiredString(map["userId"], '$path.userId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      bio: _requiredString(map["bio"], '$path.bio'),
      metFrom: _requiredString(map["metFrom"], '$path.metFrom'),
      lastInteraction: _requiredString(map["lastInteraction"], '$path.lastInteraction'),
      relationState: _requiredString(map["relationState"], '$path.relationState'),
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      conversationType: _requiredString(map["conversationType"], '$path.conversationType'),
      subtitle: _requiredString(map["subtitle"], '$path.subtitle'),
      highlightText: _requiredString(map["highlightText"], '$path.highlightText'),
      matchedField: _requiredString(map["matchedField"], '$path.matchedField'),
      source: _requiredString(map["source"], '$path.source'),
      isStarred: _requiredBool(map["isStarred"], '$path.isStarred'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "userHandle": userHandle,
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "bio": bio,
    "metFrom": metFrom,
    "lastInteraction": lastInteraction,
    "relationState": relationState,
    "conversationId": conversationId,
    "conversationType": conversationType,
    "subtitle": subtitle,
    "highlightText": highlightText,
    "matchedField": matchedField,
    "source": source,
    "isStarred": isStarred,
  };
}

final class ChatConversation {
  const ChatConversation({
    required this.id,
    required this.conversationId,
    required this.type,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    this.groupAvatarSourceHash,
    required this.creatorId,
    required this.circleId,
    required this.circleGroupId,
    required this.gatheringId,
    required this.gatheringSourceVersion,
    required this.gatheringSourceEventId,
    required this.accessMode,
    required this.postingPolicy,
    required this.entityId,
    required this.originType,
    this.originIntersectionSnapshot,
    required this.intersectionFacts,
    required this.maxSeq,
    required this.memberCount,
    required this.membersRosterRevision,
    required this.maxGroupSize,
    required this.receiptEnabled,
    required this.announcement,
    required this.announcementUpdatedBy,
    this.announcementUpdatedAt,
    required this.nameEditableByAdminOnly,
    required this.lastMessageId,
    required this.lastMessagePreview,
    required this.lastMessageType,
    required this.lastMessageTime,
    required this.messageCount,
    required this.status,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final String conversationId;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String? groupAvatarSourceHash;
  final String creatorId;
  final String circleId;
  final String circleGroupId;
  final String gatheringId;
  final int gatheringSourceVersion;
  final String gatheringSourceEventId;
  final ConversationAccessMode accessMode;
  final ConversationPostingPolicy postingPolicy;
  final String entityId;
  final String originType;
  final GreetingIntersectionSnapshot? originIntersectionSnapshot;
  final List<ContactIntersectionFact> intersectionFacts;
  final int maxSeq;
  final int memberCount;
  final int membersRosterRevision;
  final int maxGroupSize;
  final bool receiptEnabled;
  final String announcement;
  final String announcementUpdatedBy;
  final DateTime? announcementUpdatedAt;
  final bool nameEditableByAdminOnly;
  final String lastMessageId;
  final String lastMessagePreview;
  final MessageType lastMessageType;
  final DateTime lastMessageTime;
  final int messageCount;
  final String status;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory ChatConversation.fromWire(Map<String, Object?> map, [String path = "ChatConversation"]) {
    _rejectUnknownFields(map, const <String>{"id", "conversationId", "type", "title", "avatarUrl", "groupAvatarVersion", "groupAvatarSourceHash", "creatorId", "circleId", "circleGroupId", "gatheringId", "gatheringSourceVersion", "gatheringSourceEventId", "accessMode", "postingPolicy", "entityId", "originType", "originIntersectionSnapshot", "intersectionFacts", "maxSeq", "memberCount", "membersRosterRevision", "maxGroupSize", "receiptEnabled", "announcement", "announcementUpdatedBy", "announcementUpdatedAt", "nameEditableByAdminOnly", "lastMessageId", "lastMessagePreview", "lastMessageType", "lastMessageTime", "messageCount", "status", "createdAt", "updatedAt"}, path);
    return ChatConversation(
      id: _requiredString(map["id"], '$path.id'),
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      type: _requiredString(map["type"], '$path.type'),
      title: _requiredString(map["title"], '$path.title'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      groupAvatarVersion: _requiredInt(map["groupAvatarVersion"], '$path.groupAvatarVersion'),
      groupAvatarSourceHash: map["groupAvatarSourceHash"] == null ? null : _requiredString(map["groupAvatarSourceHash"], '$path.groupAvatarSourceHash'),
      creatorId: _requiredString(map["creatorId"], '$path.creatorId'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      circleGroupId: _requiredString(map["circleGroupId"], '$path.circleGroupId'),
      gatheringId: _requiredString(map["gatheringId"], '$path.gatheringId'),
      gatheringSourceVersion: _requiredInt(map["gatheringSourceVersion"], '$path.gatheringSourceVersion'),
      gatheringSourceEventId: _requiredString(map["gatheringSourceEventId"], '$path.gatheringSourceEventId'),
      accessMode: ConversationAccessMode.fromWire(map["accessMode"], '$path.accessMode'),
      postingPolicy: ConversationPostingPolicy.fromWire(map["postingPolicy"], '$path.postingPolicy'),
      entityId: _requiredString(map["entityId"], '$path.entityId'),
      originType: _requiredString(map["originType"], '$path.originType'),
      originIntersectionSnapshot: map["originIntersectionSnapshot"] == null ? null : GreetingIntersectionSnapshot.fromWire(_requiredObject(map["originIntersectionSnapshot"], '$path.originIntersectionSnapshot'), '$path.originIntersectionSnapshot'),
      intersectionFacts: List<ContactIntersectionFact>.unmodifiable(_requiredList(map["intersectionFacts"], '$path.intersectionFacts').asMap().entries.map((entry) => ContactIntersectionFact.fromWire(_requiredObject(entry.value, '$path.intersectionFacts' + '[${entry.key}]'), '$path.intersectionFacts' + '[${entry.key}]'))),
      maxSeq: _requiredInt(map["maxSeq"], '$path.maxSeq'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      membersRosterRevision: _requiredInt(map["membersRosterRevision"], '$path.membersRosterRevision'),
      maxGroupSize: _requiredInt(map["maxGroupSize"], '$path.maxGroupSize'),
      receiptEnabled: _requiredBool(map["receiptEnabled"], '$path.receiptEnabled'),
      announcement: _requiredString(map["announcement"], '$path.announcement'),
      announcementUpdatedBy: _requiredString(map["announcementUpdatedBy"], '$path.announcementUpdatedBy'),
      announcementUpdatedAt: map["announcementUpdatedAt"] == null ? null : _requiredTimestamp(map["announcementUpdatedAt"], '$path.announcementUpdatedAt'),
      nameEditableByAdminOnly: _requiredBool(map["nameEditableByAdminOnly"], '$path.nameEditableByAdminOnly'),
      lastMessageId: _requiredString(map["lastMessageId"], '$path.lastMessageId'),
      lastMessagePreview: _requiredString(map["lastMessagePreview"], '$path.lastMessagePreview'),
      lastMessageType: MessageType.fromWire(map["lastMessageType"], '$path.lastMessageType'),
      lastMessageTime: _requiredTimestamp(map["lastMessageTime"], '$path.lastMessageTime'),
      messageCount: _requiredInt(map["messageCount"], '$path.messageCount'),
      status: _requiredString(map["status"], '$path.status'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "conversationId": conversationId,
    "type": type,
    "title": title,
    "avatarUrl": avatarUrl,
    "groupAvatarVersion": groupAvatarVersion,
    if (groupAvatarSourceHash != null) "groupAvatarSourceHash": groupAvatarSourceHash!,
    "creatorId": creatorId,
    "circleId": circleId,
    "circleGroupId": circleGroupId,
    "gatheringId": gatheringId,
    "gatheringSourceVersion": gatheringSourceVersion,
    "gatheringSourceEventId": gatheringSourceEventId,
    "accessMode": accessMode.wireName,
    "postingPolicy": postingPolicy.wireName,
    "entityId": entityId,
    "originType": originType,
    if (originIntersectionSnapshot != null) "originIntersectionSnapshot": originIntersectionSnapshot!.toWire(),
    "intersectionFacts": intersectionFacts.map((value) => value.toWire()).toList(growable: false),
    "maxSeq": maxSeq,
    "memberCount": memberCount,
    "membersRosterRevision": membersRosterRevision,
    "maxGroupSize": maxGroupSize,
    "receiptEnabled": receiptEnabled,
    "announcement": announcement,
    "announcementUpdatedBy": announcementUpdatedBy,
    if (announcementUpdatedAt != null) "announcementUpdatedAt": announcementUpdatedAt!.toUtc().toIso8601String(),
    "nameEditableByAdminOnly": nameEditableByAdminOnly,
    "lastMessageId": lastMessageId,
    "lastMessagePreview": lastMessagePreview,
    "lastMessageType": lastMessageType.wireName,
    "lastMessageTime": lastMessageTime.toUtc().toIso8601String(),
    "messageCount": messageCount,
    "status": status,
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class ChatConversationTimestamp {
  const ChatConversationTimestamp({
    required this.conversationId,
    required this.type,
    required this.updatedAt,
    required this.settingsUpdatedAt,
    required this.lastMessageAt,
    required this.lastMessageTime,
    required this.lastMessagePreview,
    required this.unreadCount,
  });

  final String conversationId;
  final String type;
  final DateTime updatedAt;
  final DateTime settingsUpdatedAt;
  final DateTime lastMessageAt;
  final DateTime lastMessageTime;
  final String lastMessagePreview;
  final int unreadCount;

  factory ChatConversationTimestamp.fromWire(Map<String, Object?> map, [String path = "ChatConversationTimestamp"]) {
    _rejectUnknownFields(map, const <String>{"conversationId", "type", "updatedAt", "settingsUpdatedAt", "lastMessageAt", "lastMessageTime", "lastMessagePreview", "unreadCount"}, path);
    return ChatConversationTimestamp(
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      type: _requiredString(map["type"], '$path.type'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
      settingsUpdatedAt: _requiredTimestamp(map["settingsUpdatedAt"], '$path.settingsUpdatedAt'),
      lastMessageAt: _requiredTimestamp(map["lastMessageAt"], '$path.lastMessageAt'),
      lastMessageTime: _requiredTimestamp(map["lastMessageTime"], '$path.lastMessageTime'),
      lastMessagePreview: _requiredString(map["lastMessagePreview"], '$path.lastMessagePreview'),
      unreadCount: _requiredInt(map["unreadCount"], '$path.unreadCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": conversationId,
    "type": type,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
    "settingsUpdatedAt": settingsUpdatedAt.toUtc().toIso8601String(),
    "lastMessageAt": lastMessageAt.toUtc().toIso8601String(),
    "lastMessageTime": lastMessageTime.toUtc().toIso8601String(),
    "lastMessagePreview": lastMessagePreview,
    "unreadCount": unreadCount,
  };
}

final class ChatInboxItemView {
  const ChatInboxItemView({
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
    this.circleId,
  });

  final String id;
  final String type;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String lastMessagePreview;
  final MessageType lastMessageType;
  final DateTime lastMessageTime;
  final int lastSeq;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final String? circleId;

  factory ChatInboxItemView.fromWire(Map<String, Object?> map, [String path = "ChatInboxItemView"]) {
    _rejectUnknownFields(map, const <String>{"id", "type", "title", "avatarUrl", "groupAvatarVersion", "lastMessagePreview", "lastMessageType", "lastMessageTime", "lastSeq", "unreadCount", "mentionUnreadCount", "muted", "pinned", "circleId"}, path);
    return ChatInboxItemView(
      id: _requiredString(map["id"], '$path.id'),
      type: _requiredString(map["type"], '$path.type'),
      title: _requiredString(map["title"], '$path.title'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      groupAvatarVersion: _requiredInt(map["groupAvatarVersion"], '$path.groupAvatarVersion'),
      lastMessagePreview: _requiredString(map["lastMessagePreview"], '$path.lastMessagePreview'),
      lastMessageType: MessageType.fromWire(map["lastMessageType"], '$path.lastMessageType'),
      lastMessageTime: _requiredTimestamp(map["lastMessageTime"], '$path.lastMessageTime'),
      lastSeq: _requiredInt(map["lastSeq"], '$path.lastSeq'),
      unreadCount: _requiredInt(map["unreadCount"], '$path.unreadCount'),
      mentionUnreadCount: _requiredInt(map["mentionUnreadCount"], '$path.mentionUnreadCount'),
      muted: _requiredBool(map["muted"], '$path.muted'),
      pinned: _requiredBool(map["pinned"], '$path.pinned'),
      circleId: map["circleId"] == null ? null : _requiredString(map["circleId"], '$path.circleId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "type": type,
    "title": title,
    "avatarUrl": avatarUrl,
    "groupAvatarVersion": groupAvatarVersion,
    "lastMessagePreview": lastMessagePreview,
    "lastMessageType": lastMessageType.wireName,
    "lastMessageTime": lastMessageTime.toUtc().toIso8601String(),
    "lastSeq": lastSeq,
    "unreadCount": unreadCount,
    "mentionUnreadCount": mentionUnreadCount,
    "muted": muted,
    "pinned": pinned,
    if (circleId != null) "circleId": circleId!,
  };
}

final class ChatInboxPageSlice {
  const ChatInboxPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ChatInboxItemView> items;
  final String? nextCursor;

  factory ChatInboxPageSlice.fromWire(Map<String, Object?> map, [String path = "ChatInboxPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return ChatInboxPageSlice(
      items: List<ChatInboxItemView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatInboxItemView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ChatMessageReceipt {
  const ChatMessageReceipt({
    required this.id,
    required this.messageId,
    required this.conversationId,
    required this.userId,
    required this.readAt,
  });

  final String id;
  final String messageId;
  final String conversationId;
  final String userId;
  final DateTime readAt;

  factory ChatMessageReceipt.fromWire(Map<String, Object?> map, [String path = "ChatMessageReceipt"]) {
    _rejectUnknownFields(map, const <String>{"id", "messageId", "conversationId", "userId", "readAt"}, path);
    return ChatMessageReceipt(
      id: _requiredString(map["id"], '$path.id'),
      messageId: _requiredString(map["messageId"], '$path.messageId'),
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      userId: _requiredString(map["userId"], '$path.userId'),
      readAt: _requiredTimestamp(map["readAt"], '$path.readAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "messageId": messageId,
    "conversationId": conversationId,
    "userId": userId,
    "readAt": readAt.toUtc().toIso8601String(),
  };
}

final class ChatMessageSyncSlice {
  const ChatMessageSyncSlice({
    required this.messages,
    required this.hasMore,
  });

  final List<ChatMessageView> messages;
  final bool hasMore;

  factory ChatMessageSyncSlice.fromWire(Map<String, Object?> map, [String path = "ChatMessageSyncSlice"]) {
    _rejectUnknownFields(map, const <String>{"messages", "hasMore"}, path);
    return ChatMessageSyncSlice(
      messages: List<ChatMessageView>.unmodifiable(_requiredList(map["messages"], '$path.messages').asMap().entries.map((entry) => ChatMessageView.fromWire(_requiredObject(entry.value, '$path.messages' + '[${entry.key}]'), '$path.messages' + '[${entry.key}]'))),
      hasMore: _requiredBool(map["hasMore"], '$path.hasMore'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messages": messages.map((value) => value.toWire()).toList(growable: false),
    "hasMore": hasMore,
  };
}

final class ChatMessageView {
  const ChatMessageView({
    required this.id,
    required this.conversationId,
    required this.seq,
    required this.clientMsgId,
    required this.senderId,
    this.senderName,
    this.senderAvatar,
    required this.type,
    this.content,
    this.mediaAssetId,
    this.mediaDeliveryUrl,
    this.mediaType,
    this.mediaContentType,
    this.mediaFileSizeBytes,
    this.audioDurationMs,
    this.audioWaveform,
    this.card,
    this.replyToMessageId,
    this.mentions,
    required this.status,
    this.recalledAt,
    required this.timestamp,
  });

  final String id;
  final String conversationId;
  final int seq;
  final String clientMsgId;
  final String senderId;
  final String? senderName;
  final String? senderAvatar;
  final MessageType type;
  final String? content;
  final String? mediaAssetId;
  final String? mediaDeliveryUrl;
  final String? mediaType;
  final String? mediaContentType;
  final int? mediaFileSizeBytes;
  final int? audioDurationMs;
  final List<double>? audioWaveform;
  final MessageCard? card;
  final String? replyToMessageId;
  final List<String>? mentions;
  final MessageStatus status;
  final DateTime? recalledAt;
  final DateTime timestamp;

  factory ChatMessageView.fromWire(Map<String, Object?> map, [String path = "ChatMessageView"]) {
    _rejectUnknownFields(map, const <String>{"id", "conversationId", "seq", "clientMsgId", "senderId", "senderName", "senderAvatar", "type", "content", "mediaAssetId", "mediaDeliveryUrl", "mediaType", "mediaContentType", "mediaFileSizeBytes", "audioDurationMs", "audioWaveform", "card", "replyToMessageId", "mentions", "status", "recalledAt", "timestamp"}, path);
    return ChatMessageView(
      id: _requiredString(map["id"], '$path.id'),
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      seq: _requiredInt(map["seq"], '$path.seq'),
      clientMsgId: _requiredString(map["clientMsgId"], '$path.clientMsgId'),
      senderId: _requiredString(map["senderId"], '$path.senderId'),
      senderName: map["senderName"] == null ? null : _requiredString(map["senderName"], '$path.senderName'),
      senderAvatar: map["senderAvatar"] == null ? null : _requiredString(map["senderAvatar"], '$path.senderAvatar'),
      type: MessageType.fromWire(map["type"], '$path.type'),
      content: map["content"] == null ? null : _requiredString(map["content"], '$path.content'),
      mediaAssetId: map["mediaAssetId"] == null ? null : _requiredString(map["mediaAssetId"], '$path.mediaAssetId'),
      mediaDeliveryUrl: map["mediaDeliveryUrl"] == null ? null : _requiredString(map["mediaDeliveryUrl"], '$path.mediaDeliveryUrl'),
      mediaType: map["mediaType"] == null ? null : _requiredString(map["mediaType"], '$path.mediaType'),
      mediaContentType: map["mediaContentType"] == null ? null : _requiredString(map["mediaContentType"], '$path.mediaContentType'),
      mediaFileSizeBytes: map["mediaFileSizeBytes"] == null ? null : _requiredInt(map["mediaFileSizeBytes"], '$path.mediaFileSizeBytes'),
      audioDurationMs: map["audioDurationMs"] == null ? null : _requiredInt(map["audioDurationMs"], '$path.audioDurationMs'),
      audioWaveform: map["audioWaveform"] == null ? null : List<double>.unmodifiable(_requiredList(map["audioWaveform"], '$path.audioWaveform').asMap().entries.map((entry) => _requiredDouble(entry.value, '$path.audioWaveform' + '[${entry.key}]'))),
      card: map["card"] == null ? null : MessageCard.fromWire(_requiredObject(map["card"], '$path.card'), '$path.card'),
      replyToMessageId: map["replyToMessageId"] == null ? null : _requiredString(map["replyToMessageId"], '$path.replyToMessageId'),
      mentions: map["mentions"] == null ? null : List<String>.unmodifiable(_requiredList(map["mentions"], '$path.mentions').asMap().entries.map((entry) => _requiredString(entry.value, '$path.mentions' + '[${entry.key}]'))),
      status: MessageStatus.fromWire(map["status"], '$path.status'),
      recalledAt: map["recalledAt"] == null ? null : _requiredTimestamp(map["recalledAt"], '$path.recalledAt'),
      timestamp: _requiredTimestamp(map["timestamp"], '$path.timestamp'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "conversationId": conversationId,
    "seq": seq,
    "clientMsgId": clientMsgId,
    "senderId": senderId,
    if (senderName != null) "senderName": senderName!,
    if (senderAvatar != null) "senderAvatar": senderAvatar!,
    "type": type.wireName,
    if (content != null) "content": content!,
    if (mediaAssetId != null) "mediaAssetId": mediaAssetId!,
    if (mediaDeliveryUrl != null) "mediaDeliveryUrl": mediaDeliveryUrl!,
    if (mediaType != null) "mediaType": mediaType!,
    if (mediaContentType != null) "mediaContentType": mediaContentType!,
    if (mediaFileSizeBytes != null) "mediaFileSizeBytes": mediaFileSizeBytes!,
    if (audioDurationMs != null) "audioDurationMs": audioDurationMs!,
    if (audioWaveform != null) "audioWaveform": audioWaveform!.map((value) => value).toList(growable: false),
    if (card != null) "card": card!.toWire(),
    if (replyToMessageId != null) "replyToMessageId": replyToMessageId!,
    if (mentions != null) "mentions": mentions!.map((value) => value).toList(growable: false),
    "status": status.wireName,
    if (recalledAt != null) "recalledAt": recalledAt!.toUtc().toIso8601String(),
    "timestamp": timestamp.toUtc().toIso8601String(),
  };
}

final class ChatSendMessageResult {
  const ChatSendMessageResult({
    required this.messageId,
    required this.seq,
    required this.timestamp,
  });

  final String messageId;
  final int seq;
  final DateTime timestamp;

  factory ChatSendMessageResult.fromWire(Map<String, Object?> map, [String path = "ChatSendMessageResult"]) {
    _rejectUnknownFields(map, const <String>{"messageId", "seq", "timestamp"}, path);
    return ChatSendMessageResult(
      messageId: _requiredString(map["messageId"], '$path.messageId'),
      seq: _requiredInt(map["seq"], '$path.seq'),
      timestamp: _requiredTimestamp(map["timestamp"], '$path.timestamp'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messageId": messageId,
    "seq": seq,
    "timestamp": timestamp.toUtc().toIso8601String(),
  };
}

final class ContactHomePageSlice {
  const ContactHomePageSlice({
    required this.items,
  });

  final List<ContactHomeRow> items;

  factory ContactHomePageSlice.fromWire(Map<String, Object?> map, [String path = "ContactHomePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ContactHomePageSlice(
      items: List<ContactHomeRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ContactHomeRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ContactHomeRow {
  const ContactHomeRow({
    required this.id,
    required this.kind,
    required this.objectId,
    this.userId,
    required this.userHandle,
    this.conversationId,
    this.circleId,
    this.circleGroupId,
    this.entityId,
    required this.title,
    required this.subtitle,
    required this.avatarUrl,
    this.relationState,
    required this.intersectionFacts,
    this.sourceEntityTitle,
    this.sourceCircleTitle,
    this.memberCount,
    required this.contactCount,
    this.lastActiveAt,
    required this.sortKey,
    this.isStarred,
  });

  final String id;
  final String kind;
  final String objectId;
  final String? userId;
  final String userHandle;
  final String? conversationId;
  final String? circleId;
  final String? circleGroupId;
  final String? entityId;
  final String title;
  final String subtitle;
  final String avatarUrl;
  final String? relationState;
  final List<ContactIntersectionFact> intersectionFacts;
  final String? sourceEntityTitle;
  final String? sourceCircleTitle;
  final int? memberCount;
  final int contactCount;
  final DateTime? lastActiveAt;
  final String sortKey;
  final bool? isStarred;

  factory ContactHomeRow.fromWire(Map<String, Object?> map, [String path = "ContactHomeRow"]) {
    _rejectUnknownFields(map, const <String>{"id", "kind", "objectId", "userId", "userHandle", "conversationId", "circleId", "circleGroupId", "entityId", "title", "subtitle", "avatarUrl", "relationState", "intersectionFacts", "sourceEntityTitle", "sourceCircleTitle", "memberCount", "contactCount", "lastActiveAt", "sortKey", "isStarred"}, path);
    return ContactHomeRow(
      id: _requiredString(map["id"], '$path.id'),
      kind: _requiredString(map["kind"], '$path.kind'),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      userId: map["userId"] == null ? null : _requiredString(map["userId"], '$path.userId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      conversationId: map["conversationId"] == null ? null : _requiredString(map["conversationId"], '$path.conversationId'),
      circleId: map["circleId"] == null ? null : _requiredString(map["circleId"], '$path.circleId'),
      circleGroupId: map["circleGroupId"] == null ? null : _requiredString(map["circleGroupId"], '$path.circleGroupId'),
      entityId: map["entityId"] == null ? null : _requiredString(map["entityId"], '$path.entityId'),
      title: _requiredString(map["title"], '$path.title'),
      subtitle: _requiredString(map["subtitle"], '$path.subtitle'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      relationState: map["relationState"] == null ? null : _requiredString(map["relationState"], '$path.relationState'),
      intersectionFacts: List<ContactIntersectionFact>.unmodifiable(_requiredList(map["intersectionFacts"], '$path.intersectionFacts').asMap().entries.map((entry) => ContactIntersectionFact.fromWire(_requiredObject(entry.value, '$path.intersectionFacts' + '[${entry.key}]'), '$path.intersectionFacts' + '[${entry.key}]'))),
      sourceEntityTitle: map["sourceEntityTitle"] == null ? null : _requiredString(map["sourceEntityTitle"], '$path.sourceEntityTitle'),
      sourceCircleTitle: map["sourceCircleTitle"] == null ? null : _requiredString(map["sourceCircleTitle"], '$path.sourceCircleTitle'),
      memberCount: map["memberCount"] == null ? null : _requiredInt(map["memberCount"], '$path.memberCount'),
      contactCount: _requiredInt(map["contactCount"], '$path.contactCount'),
      lastActiveAt: map["lastActiveAt"] == null ? null : _requiredTimestamp(map["lastActiveAt"], '$path.lastActiveAt'),
      sortKey: _requiredString(map["sortKey"], '$path.sortKey'),
      isStarred: map["isStarred"] == null ? null : _requiredBool(map["isStarred"], '$path.isStarred'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "kind": kind,
    "objectId": objectId,
    if (userId != null) "userId": userId!,
    "userHandle": userHandle,
    if (conversationId != null) "conversationId": conversationId!,
    if (circleId != null) "circleId": circleId!,
    if (circleGroupId != null) "circleGroupId": circleGroupId!,
    if (entityId != null) "entityId": entityId!,
    "title": title,
    "subtitle": subtitle,
    "avatarUrl": avatarUrl,
    if (relationState != null) "relationState": relationState!,
    "intersectionFacts": intersectionFacts.map((value) => value.toWire()).toList(growable: false),
    if (sourceEntityTitle != null) "sourceEntityTitle": sourceEntityTitle!,
    if (sourceCircleTitle != null) "sourceCircleTitle": sourceCircleTitle!,
    if (memberCount != null) "memberCount": memberCount!,
    "contactCount": contactCount,
    if (lastActiveAt != null) "lastActiveAt": lastActiveAt!.toUtc().toIso8601String(),
    "sortKey": sortKey,
    if (isStarred != null) "isStarred": isStarred!,
  };
}

final class ContactIntersectionFact {
  const ContactIntersectionFact({
    required this.intersectionId,
    required this.kind,
    required this.dimension,
    required this.intersectionClass,
    required this.primaryText,
  });

  final String intersectionId;
  final String kind;
  final String dimension;
  final String intersectionClass;
  final String primaryText;

  factory ContactIntersectionFact.fromWire(Map<String, Object?> map, [String path = "ContactIntersectionFact"]) {
    _rejectUnknownFields(map, const <String>{"intersectionId", "kind", "dimension", "intersectionClass", "primaryText"}, path);
    return ContactIntersectionFact(
      intersectionId: _requiredNonBlankString(map["intersectionId"], '$path.intersectionId'),
      kind: _requiredNonBlankString(map["kind"], '$path.kind'),
      dimension: _requiredNonBlankString(map["dimension"], '$path.dimension'),
      intersectionClass: _requiredNonBlankString(map["intersectionClass"], '$path.intersectionClass'),
      primaryText: _requiredNonBlankString(map["primaryText"], '$path.primaryText'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "intersectionId": intersectionId,
    "kind": kind,
    "dimension": dimension,
    "intersectionClass": intersectionClass,
    "primaryText": primaryText,
  };
}

final class ContactPageSlice {
  const ContactPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ChatContactListRow> items;
  final String? nextCursor;

  factory ContactPageSlice.fromWire(Map<String, Object?> map, [String path = "ContactPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return ContactPageSlice(
      items: List<ChatContactListRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatContactListRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ConversationAssetPage {
  const ConversationAssetPage({
    required this.items,
    this.nextBeforeSeq,
  });

  final List<ConversationAssetView> items;
  final int? nextBeforeSeq;

  factory ConversationAssetPage.fromWire(Map<String, Object?> map, [String path = "ConversationAssetPage"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextBeforeSeq"}, path);
    return ConversationAssetPage(
      items: List<ConversationAssetView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ConversationAssetView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextBeforeSeq: map["nextBeforeSeq"] == null ? null : _requiredInt(map["nextBeforeSeq"], '$path.nextBeforeSeq'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextBeforeSeq != null) "nextBeforeSeq": nextBeforeSeq!,
  };
}

final class ConversationAssetView {
  const ConversationAssetView({
    required this.messageId,
    required this.seq,
    required this.mediaAssetId,
    required this.messageType,
    required this.senderId,
    this.senderName,
    this.fileName,
    this.mediaDeliveryUrl,
    this.mediaContentType,
    this.mediaFileSizeBytes,
    required this.createdAt,
  });

  final String messageId;
  final int seq;
  final String mediaAssetId;
  final String messageType;
  final String senderId;
  final String? senderName;
  final String? fileName;
  final String? mediaDeliveryUrl;
  final String? mediaContentType;
  final int? mediaFileSizeBytes;
  final DateTime createdAt;

  factory ConversationAssetView.fromWire(Map<String, Object?> map, [String path = "ConversationAssetView"]) {
    _rejectUnknownFields(map, const <String>{"messageId", "seq", "mediaAssetId", "messageType", "senderId", "senderName", "fileName", "mediaDeliveryUrl", "mediaContentType", "mediaFileSizeBytes", "createdAt"}, path);
    return ConversationAssetView(
      messageId: _requiredNonBlankString(map["messageId"], '$path.messageId'),
      seq: _requiredInt(map["seq"], '$path.seq'),
      mediaAssetId: _requiredNonBlankString(map["mediaAssetId"], '$path.mediaAssetId'),
      messageType: _requiredNonBlankString(map["messageType"], '$path.messageType'),
      senderId: _requiredNonBlankString(map["senderId"], '$path.senderId'),
      senderName: map["senderName"] == null ? null : _requiredString(map["senderName"], '$path.senderName'),
      fileName: map["fileName"] == null ? null : _requiredString(map["fileName"], '$path.fileName'),
      mediaDeliveryUrl: map["mediaDeliveryUrl"] == null ? null : _requiredString(map["mediaDeliveryUrl"], '$path.mediaDeliveryUrl'),
      mediaContentType: map["mediaContentType"] == null ? null : _requiredString(map["mediaContentType"], '$path.mediaContentType'),
      mediaFileSizeBytes: map["mediaFileSizeBytes"] == null ? null : _requiredInt(map["mediaFileSizeBytes"], '$path.mediaFileSizeBytes'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messageId": messageId,
    "seq": seq,
    "mediaAssetId": mediaAssetId,
    "messageType": messageType,
    "senderId": senderId,
    if (senderName != null) "senderName": senderName!,
    if (fileName != null) "fileName": fileName!,
    if (mediaDeliveryUrl != null) "mediaDeliveryUrl": mediaDeliveryUrl!,
    if (mediaContentType != null) "mediaContentType": mediaContentType!,
    if (mediaFileSizeBytes != null) "mediaFileSizeBytes": mediaFileSizeBytes!,
    "createdAt": createdAt.toUtc().toIso8601String(),
  };
}

final class ConversationBatchSlice {
  const ConversationBatchSlice({
    required this.items,
  });

  final List<ChatConversation> items;

  factory ConversationBatchSlice.fromWire(Map<String, Object?> map, [String path = "ConversationBatchSlice"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ConversationBatchSlice(
      items: List<ChatConversation>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatConversation.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ConversationCommandAck {
  const ConversationCommandAck({
    required this.status,
  });

  final String status;

  factory ConversationCommandAck.fromWire(Map<String, Object?> map, [String path = "ConversationCommandAck"]) {
    _rejectUnknownFields(map, const <String>{"status"}, path);
    return ConversationCommandAck(
      status: _requiredString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status,
  };
}

final class ConversationMemberListRow {
  const ConversationMemberListRow({
    required this.userId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.role,
    required this.memberType,
    this.joinedAt,
    required this.isCurrentUser,
  });

  final String userId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String role;
  final String memberType;
  final DateTime? joinedAt;
  final bool isCurrentUser;

  factory ConversationMemberListRow.fromWire(Map<String, Object?> map, [String path = "ConversationMemberListRow"]) {
    _rejectUnknownFields(map, const <String>{"userId", "userHandle", "displayName", "avatarUrl", "role", "memberType", "joinedAt", "isCurrentUser"}, path);
    return ConversationMemberListRow(
      userId: _requiredString(map["userId"], '$path.userId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      role: _requiredString(map["role"], '$path.role'),
      memberType: _requiredString(map["memberType"], '$path.memberType'),
      joinedAt: map["joinedAt"] == null ? null : _requiredTimestamp(map["joinedAt"], '$path.joinedAt'),
      isCurrentUser: _requiredBool(map["isCurrentUser"], '$path.isCurrentUser'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "userHandle": userHandle,
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "role": role,
    "memberType": memberType,
    if (joinedAt != null) "joinedAt": joinedAt!.toUtc().toIso8601String(),
    "isCurrentUser": isCurrentUser,
  };
}

final class ConversationMemberPageSlice {
  const ConversationMemberPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ConversationMemberListRow> items;
  final String? nextCursor;

  factory ConversationMemberPageSlice.fromWire(Map<String, Object?> map, [String path = "ConversationMemberPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return ConversationMemberPageSlice(
      items: List<ConversationMemberListRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ConversationMemberListRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ConversationMembershipCommandAck {
  const ConversationMembershipCommandAck({
    required this.status,
  });

  final String status;

  factory ConversationMembershipCommandAck.fromWire(Map<String, Object?> map, [String path = "ConversationMembershipCommandAck"]) {
    _rejectUnknownFields(map, const <String>{"status"}, path);
    return ConversationMembershipCommandAck(
      status: _requiredString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status,
  };
}

final class ConversationPageSlice {
  const ConversationPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<ChatConversation> items;
  final String? nextCursor;

  factory ConversationPageSlice.fromWire(Map<String, Object?> map, [String path = "ConversationPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return ConversationPageSlice(
      items: List<ChatConversation>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatConversation.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class ConversationTimestampIndexSlice {
  const ConversationTimestampIndexSlice({
    required this.items,
  });

  final List<ChatConversationTimestamp> items;

  factory ConversationTimestampIndexSlice.fromWire(Map<String, Object?> map, [String path = "ConversationTimestampIndexSlice"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return ConversationTimestampIndexSlice(
      items: List<ChatConversationTimestamp>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatConversationTimestamp.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class ConversationUserStateCommandAck {
  const ConversationUserStateCommandAck({
    required this.status,
  });

  final String status;

  factory ConversationUserStateCommandAck.fromWire(Map<String, Object?> map, [String path = "ConversationUserStateCommandAck"]) {
    _rejectUnknownFields(map, const <String>{"status"}, path);
    return ConversationUserStateCommandAck(
      status: _requiredString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status,
  };
}

final class GatheringAssetIndexItem {
  const GatheringAssetIndexItem({
    required this.messageId,
    required this.seq,
    required this.mediaAssetId,
    required this.messageType,
    required this.createdAt,
  });

  final String messageId;
  final int seq;
  final String mediaAssetId;
  final String messageType;
  final DateTime createdAt;

  factory GatheringAssetIndexItem.fromWire(Map<String, Object?> map, [String path = "GatheringAssetIndexItem"]) {
    _rejectUnknownFields(map, const <String>{"messageId", "seq", "mediaAssetId", "messageType", "createdAt"}, path);
    return GatheringAssetIndexItem(
      messageId: _requiredNonBlankString(map["messageId"], '$path.messageId'),
      seq: _requiredInt(map["seq"], '$path.seq'),
      mediaAssetId: _requiredNonBlankString(map["mediaAssetId"], '$path.mediaAssetId'),
      messageType: _requiredNonBlankString(map["messageType"], '$path.messageType'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messageId": messageId,
    "seq": seq,
    "mediaAssetId": mediaAssetId,
    "messageType": messageType,
    "createdAt": createdAt.toUtc().toIso8601String(),
  };
}

final class GatheringChatAccessSummary {
  const GatheringChatAccessSummary({
    required this.gatheringId,
    required this.conversationId,
    required this.accessMode,
    required this.postingPolicy,
    required this.viewerRole,
    required this.canPost,
  });

  final String gatheringId;
  final String conversationId;
  final ConversationAccessMode accessMode;
  final ConversationPostingPolicy postingPolicy;
  final String viewerRole;
  final bool canPost;

  factory GatheringChatAccessSummary.fromWire(Map<String, Object?> map, [String path = "GatheringChatAccessSummary"]) {
    _rejectUnknownFields(map, const <String>{"gatheringId", "conversationId", "accessMode", "postingPolicy", "viewerRole", "canPost"}, path);
    return GatheringChatAccessSummary(
      gatheringId: _requiredNonBlankString(map["gatheringId"], '$path.gatheringId'),
      conversationId: _requiredNonBlankString(map["conversationId"], '$path.conversationId'),
      accessMode: ConversationAccessMode.fromWire(map["accessMode"], '$path.accessMode'),
      postingPolicy: ConversationPostingPolicy.fromWire(map["postingPolicy"], '$path.postingPolicy'),
      viewerRole: _requiredString(map["viewerRole"], '$path.viewerRole'),
      canPost: _requiredBool(map["canPost"], '$path.canPost'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": gatheringId,
    "conversationId": conversationId,
    "accessMode": accessMode.wireName,
    "postingPolicy": postingPolicy.wireName,
    "viewerRole": viewerRole,
    "canPost": canPost,
  };
}

final class GatheringChatBoardSlice {
  const GatheringChatBoardSlice({
    required this.access,
    this.pinnedAnnouncement,
    required this.assets,
  });

  final GatheringChatAccessSummary access;
  final GatheringPinnedAnnouncement? pinnedAnnouncement;
  final List<GatheringAssetIndexItem> assets;

  factory GatheringChatBoardSlice.fromWire(Map<String, Object?> map, [String path = "GatheringChatBoardSlice"]) {
    _rejectUnknownFields(map, const <String>{"access", "pinnedAnnouncement", "assets"}, path);
    return GatheringChatBoardSlice(
      access: GatheringChatAccessSummary.fromWire(_requiredObject(map["access"], '$path.access'), '$path.access'),
      pinnedAnnouncement: map["pinnedAnnouncement"] == null ? null : GatheringPinnedAnnouncement.fromWire(_requiredObject(map["pinnedAnnouncement"], '$path.pinnedAnnouncement'), '$path.pinnedAnnouncement'),
      assets: List<GatheringAssetIndexItem>.unmodifiable(_requiredList(map["assets"], '$path.assets').asMap().entries.map((entry) => GatheringAssetIndexItem.fromWire(_requiredObject(entry.value, '$path.assets' + '[${entry.key}]'), '$path.assets' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "access": access.toWire(),
    if (pinnedAnnouncement != null) "pinnedAnnouncement": pinnedAnnouncement!.toWire(),
    "assets": assets.map((value) => value.toWire()).toList(growable: false),
  };
}

final class GatheringPinnedAnnouncement {
  const GatheringPinnedAnnouncement({
    required this.content,
    required this.updatedBy,
    required this.updatedAt,
  });

  final String content;
  final String updatedBy;
  final DateTime updatedAt;

  factory GatheringPinnedAnnouncement.fromWire(Map<String, Object?> map, [String path = "GatheringPinnedAnnouncement"]) {
    _rejectUnknownFields(map, const <String>{"content", "updatedBy", "updatedAt"}, path);
    return GatheringPinnedAnnouncement(
      content: _requiredNonBlankString(map["content"], '$path.content'),
      updatedBy: _requiredNonBlankString(map["updatedBy"], '$path.updatedBy'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "content": content,
    "updatedBy": updatedBy,
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class GroupCandidatePageSlice {
  const GroupCandidatePageSlice({
    required this.items,
  });

  final List<GroupCandidateRow> items;

  factory GroupCandidatePageSlice.fromWire(Map<String, Object?> map, [String path = "GroupCandidatePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return GroupCandidatePageSlice(
      items: List<GroupCandidateRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => GroupCandidateRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class GroupCandidateRow {
  const GroupCandidateRow({
    required this.userId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.bio,
    required this.metFrom,
    required this.lastInteraction,
    required this.relationState,
    required this.source,
    required this.isStarred,
  });

  final String userId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final String bio;
  final String metFrom;
  final String lastInteraction;
  final RelationshipState relationState;
  final ChatContactSource source;
  final bool isStarred;

  factory GroupCandidateRow.fromWire(Map<String, Object?> map, [String path = "GroupCandidateRow"]) {
    _rejectUnknownFields(map, const <String>{"userId", "userHandle", "displayName", "avatarUrl", "bio", "metFrom", "lastInteraction", "relationState", "source", "isStarred"}, path);
    return GroupCandidateRow(
      userId: _requiredString(map["userId"], '$path.userId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      bio: _requiredString(map["bio"], '$path.bio'),
      metFrom: _requiredString(map["metFrom"], '$path.metFrom'),
      lastInteraction: _requiredString(map["lastInteraction"], '$path.lastInteraction'),
      relationState: RelationshipState.fromWire(map["relationState"], '$path.relationState'),
      source: ChatContactSource.fromWire(map["source"], '$path.source'),
      isStarred: _requiredBool(map["isStarred"], '$path.isStarred'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "userHandle": userHandle,
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "bio": bio,
    "metFrom": metFrom,
    "lastInteraction": lastInteraction,
    "relationState": relationState.wireName,
    "source": source.wireName,
    "isStarred": isStarred,
  };
}

final class GroupHome {
  const GroupHome({
    required this.conversationId,
    required this.title,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    required this.circleId,
    required this.circleGroupId,
    required this.gatheringId,
    required this.entityId,
    required this.sourceEntityTitle,
    required this.sourceCircleTitle,
    required this.memberCount,
    required this.announcement,
    required this.capabilities,
    required this.originType,
    required this.accessMode,
    required this.postingPolicy,
    required this.canManageMembers,
    required this.canDissolve,
  });

  final String conversationId;
  final String title;
  final String avatarUrl;
  final int groupAvatarVersion;
  final String circleId;
  final String circleGroupId;
  final String gatheringId;
  final String entityId;
  final String sourceEntityTitle;
  final String sourceCircleTitle;
  final int memberCount;
  final String announcement;
  final List<String> capabilities;
  final String originType;
  final ConversationAccessMode accessMode;
  final ConversationPostingPolicy postingPolicy;
  final bool canManageMembers;
  final bool canDissolve;

  factory GroupHome.fromWire(Map<String, Object?> map, [String path = "GroupHome"]) {
    _rejectUnknownFields(map, const <String>{"conversationId", "title", "avatarUrl", "groupAvatarVersion", "circleId", "circleGroupId", "gatheringId", "entityId", "sourceEntityTitle", "sourceCircleTitle", "memberCount", "announcement", "capabilities", "originType", "accessMode", "postingPolicy", "canManageMembers", "canDissolve"}, path);
    return GroupHome(
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      title: _requiredString(map["title"], '$path.title'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      groupAvatarVersion: _requiredInt(map["groupAvatarVersion"], '$path.groupAvatarVersion'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      circleGroupId: _requiredString(map["circleGroupId"], '$path.circleGroupId'),
      gatheringId: _requiredString(map["gatheringId"], '$path.gatheringId'),
      entityId: _requiredString(map["entityId"], '$path.entityId'),
      sourceEntityTitle: _requiredString(map["sourceEntityTitle"], '$path.sourceEntityTitle'),
      sourceCircleTitle: _requiredString(map["sourceCircleTitle"], '$path.sourceCircleTitle'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
      announcement: _requiredString(map["announcement"], '$path.announcement'),
      capabilities: List<String>.unmodifiable(_requiredList(map["capabilities"], '$path.capabilities').asMap().entries.map((entry) => _requiredString(entry.value, '$path.capabilities' + '[${entry.key}]'))),
      originType: _requiredString(map["originType"], '$path.originType'),
      accessMode: ConversationAccessMode.fromWire(map["accessMode"], '$path.accessMode'),
      postingPolicy: ConversationPostingPolicy.fromWire(map["postingPolicy"], '$path.postingPolicy'),
      canManageMembers: _requiredBool(map["canManageMembers"], '$path.canManageMembers'),
      canDissolve: _requiredBool(map["canDissolve"], '$path.canDissolve'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": conversationId,
    "title": title,
    "avatarUrl": avatarUrl,
    "groupAvatarVersion": groupAvatarVersion,
    "circleId": circleId,
    "circleGroupId": circleGroupId,
    "gatheringId": gatheringId,
    "entityId": entityId,
    "sourceEntityTitle": sourceEntityTitle,
    "sourceCircleTitle": sourceCircleTitle,
    "memberCount": memberCount,
    "announcement": announcement,
    "capabilities": capabilities.map((value) => value).toList(growable: false),
    "originType": originType,
    "accessMode": accessMode.wireName,
    "postingPolicy": postingPolicy.wireName,
    "canManageMembers": canManageMembers,
    "canDissolve": canDissolve,
  };
}

final class MessageCard {
  const MessageCard({
    required this.kind,
    required this.title,
    this.objectRef,
    this.subtitle,
    this.thumbnailUrl,
    this.deeplink,
    this.landingUrl,
    this.shareText,
    this.message,
    required this.attributes,
  });

  final MessageCardKind kind;
  final String title;
  final MessageCardObjectRef? objectRef;
  final String? subtitle;
  final String? thumbnailUrl;
  final String? deeplink;
  final String? landingUrl;
  final String? shareText;
  final String? message;
  final List<MessageCardAttribute> attributes;

  factory MessageCard.fromWire(Map<String, Object?> map, [String path = "MessageCard"]) {
    _rejectUnknownFields(map, const <String>{"kind", "title", "objectRef", "subtitle", "thumbnailUrl", "deeplink", "landingUrl", "shareText", "message", "attributes"}, path);
    return MessageCard(
      kind: MessageCardKind.fromWire(map["kind"], '$path.kind'),
      title: _requiredString(map["title"], '$path.title'),
      objectRef: map["objectRef"] == null ? null : MessageCardObjectRef.fromWire(_requiredObject(map["objectRef"], '$path.objectRef'), '$path.objectRef'),
      subtitle: map["subtitle"] == null ? null : _requiredString(map["subtitle"], '$path.subtitle'),
      thumbnailUrl: map["thumbnailUrl"] == null ? null : _requiredString(map["thumbnailUrl"], '$path.thumbnailUrl'),
      deeplink: map["deeplink"] == null ? null : _requiredString(map["deeplink"], '$path.deeplink'),
      landingUrl: map["landingUrl"] == null ? null : _requiredString(map["landingUrl"], '$path.landingUrl'),
      shareText: map["shareText"] == null ? null : _requiredString(map["shareText"], '$path.shareText'),
      message: map["message"] == null ? null : _requiredString(map["message"], '$path.message'),
      attributes: List<MessageCardAttribute>.unmodifiable(_requiredList(map["attributes"], '$path.attributes').asMap().entries.map((entry) => MessageCardAttribute.fromWire(_requiredObject(entry.value, '$path.attributes' + '[${entry.key}]'), '$path.attributes' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "kind": kind.wireName,
    "title": title,
    if (objectRef != null) "objectRef": objectRef!.toWire(),
    if (subtitle != null) "subtitle": subtitle!,
    if (thumbnailUrl != null) "thumbnailUrl": thumbnailUrl!,
    if (deeplink != null) "deeplink": deeplink!,
    if (landingUrl != null) "landingUrl": landingUrl!,
    if (shareText != null) "shareText": shareText!,
    if (message != null) "message": message!,
    "attributes": attributes.map((value) => value.toWire()).toList(growable: false),
  };
}

final class MessageCardAttribute {
  const MessageCardAttribute({
    required this.name,
    required this.value,
  });

  final String name;
  final String value;

  factory MessageCardAttribute.fromWire(Map<String, Object?> map, [String path = "MessageCardAttribute"]) {
    _rejectUnknownFields(map, const <String>{"name", "value"}, path);
    return MessageCardAttribute(
      name: _requiredString(map["name"], '$path.name'),
      value: _requiredString(map["value"], '$path.value'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "name": name,
    "value": value,
  };
}

final class MessageCardObjectRef {
  const MessageCardObjectRef({
    required this.objectTypeRef,
    required this.objectId,
    required this.routeId,
  });

  final String objectTypeRef;
  final String objectId;
  final String routeId;

  factory MessageCardObjectRef.fromWire(Map<String, Object?> map, [String path = "MessageCardObjectRef"]) {
    _rejectUnknownFields(map, const <String>{"objectTypeRef", "objectId", "routeId"}, path);
    return MessageCardObjectRef(
      objectTypeRef: _requiredString(map["objectTypeRef"], '$path.objectTypeRef'),
      objectId: _requiredString(map["objectId"], '$path.objectId'),
      routeId: _requiredString(map["routeId"], '$path.routeId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "objectTypeRef": objectTypeRef,
    "objectId": objectId,
    "routeId": routeId,
  };
}

final class MessageCommandAck {
  const MessageCommandAck({
    required this.status,
  });

  final String status;

  factory MessageCommandAck.fromWire(Map<String, Object?> map, [String path = "MessageCommandAck"]) {
    _rejectUnknownFields(map, const <String>{"status"}, path);
    return MessageCommandAck(
      status: _requiredString(map["status"], '$path.status'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "status": status,
  };
}

final class MessageHomePageSlice {
  const MessageHomePageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<MessageHomeRow> items;
  final String? nextCursor;

  factory MessageHomePageSlice.fromWire(Map<String, Object?> map, [String path = "MessageHomePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return MessageHomePageSlice(
      items: List<MessageHomeRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => MessageHomeRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class MessageHomeRow {
  const MessageHomeRow({
    required this.id,
    required this.kind,
    required this.conversationId,
    required this.notificationId,
    required this.conversationType,
    required this.title,
    required this.summary,
    required this.avatarUrl,
    required this.groupAvatarVersion,
    this.lastActiveAt,
    required this.unreadCount,
    required this.mentionUnreadCount,
    required this.muted,
    required this.pinned,
    required this.notificationType,
    required this.read,
  });

  final String id;
  final String kind;
  final String conversationId;
  final String notificationId;
  final String conversationType;
  final String title;
  final String summary;
  final String avatarUrl;
  final int groupAvatarVersion;
  final DateTime? lastActiveAt;
  final int unreadCount;
  final int mentionUnreadCount;
  final bool muted;
  final bool pinned;
  final String notificationType;
  final bool read;

  factory MessageHomeRow.fromWire(Map<String, Object?> map, [String path = "MessageHomeRow"]) {
    _rejectUnknownFields(map, const <String>{"id", "kind", "conversationId", "notificationId", "conversationType", "title", "summary", "avatarUrl", "groupAvatarVersion", "lastActiveAt", "unreadCount", "mentionUnreadCount", "muted", "pinned", "notificationType", "read"}, path);
    return MessageHomeRow(
      id: _requiredString(map["id"], '$path.id'),
      kind: _requiredString(map["kind"], '$path.kind'),
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      notificationId: _requiredString(map["notificationId"], '$path.notificationId'),
      conversationType: _requiredString(map["conversationType"], '$path.conversationType'),
      title: _requiredString(map["title"], '$path.title'),
      summary: _requiredString(map["summary"], '$path.summary'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      groupAvatarVersion: _requiredInt(map["groupAvatarVersion"], '$path.groupAvatarVersion'),
      lastActiveAt: map["lastActiveAt"] == null ? null : _requiredTimestamp(map["lastActiveAt"], '$path.lastActiveAt'),
      unreadCount: _requiredInt(map["unreadCount"], '$path.unreadCount'),
      mentionUnreadCount: _requiredInt(map["mentionUnreadCount"], '$path.mentionUnreadCount'),
      muted: _requiredBool(map["muted"], '$path.muted'),
      pinned: _requiredBool(map["pinned"], '$path.pinned'),
      notificationType: _requiredString(map["notificationType"], '$path.notificationType'),
      read: _requiredBool(map["read"], '$path.read'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "kind": kind,
    "conversationId": conversationId,
    "notificationId": notificationId,
    "conversationType": conversationType,
    "title": title,
    "summary": summary,
    "avatarUrl": avatarUrl,
    "groupAvatarVersion": groupAvatarVersion,
    if (lastActiveAt != null) "lastActiveAt": lastActiveAt!.toUtc().toIso8601String(),
    "unreadCount": unreadCount,
    "mentionUnreadCount": mentionUnreadCount,
    "muted": muted,
    "pinned": pinned,
    "notificationType": notificationType,
    "read": read,
  };
}

final class MessagePageSlice {
  const MessagePageSlice({
    required this.items,
    this.nextBeforeSeq,
  });

  final List<ChatMessageView> items;
  final int? nextBeforeSeq;

  factory MessagePageSlice.fromWire(Map<String, Object?> map, [String path = "MessagePageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextBeforeSeq"}, path);
    return MessagePageSlice(
      items: List<ChatMessageView>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatMessageView.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextBeforeSeq: map["nextBeforeSeq"] == null ? null : _requiredInt(map["nextBeforeSeq"], '$path.nextBeforeSeq'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextBeforeSeq != null) "nextBeforeSeq": nextBeforeSeq!,
  };
}

final class MessageReceiptPageSlice {
  const MessageReceiptPageSlice({
    required this.items,
  });

  final List<ChatMessageReceipt> items;

  factory MessageReceiptPageSlice.fromWire(Map<String, Object?> map, [String path = "MessageReceiptPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items"}, path);
    return MessageReceiptPageSlice(
      items: List<ChatMessageReceipt>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => ChatMessageReceipt.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
  };
}

final class SelectableGroupContactMemberRow {
  const SelectableGroupContactMemberRow({
    required this.userId,
    required this.userHandle,
    required this.displayName,
    required this.avatarUrl,
    required this.relationState,
    required this.source,
  });

  final String userId;
  final String userHandle;
  final String displayName;
  final String avatarUrl;
  final RelationshipState relationState;
  final ChatContactSource source;

  factory SelectableGroupContactMemberRow.fromWire(Map<String, Object?> map, [String path = "SelectableGroupContactMemberRow"]) {
    _rejectUnknownFields(map, const <String>{"userId", "userHandle", "displayName", "avatarUrl", "relationState", "source"}, path);
    return SelectableGroupContactMemberRow(
      userId: _requiredString(map["userId"], '$path.userId'),
      userHandle: _requiredString(map["userHandle"], '$path.userHandle'),
      displayName: _requiredString(map["displayName"], '$path.displayName'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      relationState: RelationshipState.fromWire(map["relationState"], '$path.relationState'),
      source: ChatContactSource.fromWire(map["source"], '$path.source'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "userHandle": userHandle,
    "displayName": displayName,
    "avatarUrl": avatarUrl,
    "relationState": relationState.wireName,
    "source": source.wireName,
  };
}

final class SelectableGroupContactPageSlice {
  const SelectableGroupContactPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<SelectableGroupContactMemberRow> items;
  final String? nextCursor;

  factory SelectableGroupContactPageSlice.fromWire(Map<String, Object?> map, [String path = "SelectableGroupContactPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return SelectableGroupContactPageSlice(
      items: List<SelectableGroupContactMemberRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => SelectableGroupContactMemberRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class SelectableGroupConversationPageSlice {
  const SelectableGroupConversationPageSlice({
    required this.items,
    this.nextCursor,
  });

  final List<SelectableGroupConversationRow> items;
  final String? nextCursor;

  factory SelectableGroupConversationPageSlice.fromWire(Map<String, Object?> map, [String path = "SelectableGroupConversationPageSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return SelectableGroupConversationPageSlice(
      items: List<SelectableGroupConversationRow>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => SelectableGroupConversationRow.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class SelectableGroupConversationRow {
  const SelectableGroupConversationRow({
    required this.conversationId,
    required this.title,
    required this.avatarUrl,
    required this.circleId,
    required this.friendMemberCount,
    required this.memberCount,
  });

  final String conversationId;
  final String title;
  final String avatarUrl;
  final String circleId;
  final int friendMemberCount;
  final int memberCount;

  factory SelectableGroupConversationRow.fromWire(Map<String, Object?> map, [String path = "SelectableGroupConversationRow"]) {
    _rejectUnknownFields(map, const <String>{"conversationId", "title", "avatarUrl", "circleId", "friendMemberCount", "memberCount"}, path);
    return SelectableGroupConversationRow(
      conversationId: _requiredString(map["conversationId"], '$path.conversationId'),
      title: _requiredString(map["title"], '$path.title'),
      avatarUrl: _requiredString(map["avatarUrl"], '$path.avatarUrl'),
      circleId: _requiredString(map["circleId"], '$path.circleId'),
      friendMemberCount: _requiredInt(map["friendMemberCount"], '$path.friendMemberCount'),
      memberCount: _requiredInt(map["memberCount"], '$path.memberCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "conversationId": conversationId,
    "title": title,
    "avatarUrl": avatarUrl,
    "circleId": circleId,
    "friendMemberCount": friendMemberCount,
    "memberCount": memberCount,
  };
}

ChatConversation decodeChatConversation(Object? response) =>
    ChatConversation.fromWire(_requiredObject(response, "ChatConversation"), "ChatConversation");

ChatInboxPageSlice decodeChatInboxPageSlice(Object? response) =>
    ChatInboxPageSlice.fromWire(_requiredObject(response, "ChatInboxPageSlice"), "ChatInboxPageSlice");

ChatMessageSyncSlice decodeChatMessageSyncSlice(Object? response) =>
    ChatMessageSyncSlice.fromWire(_requiredObject(response, "ChatMessageSyncSlice"), "ChatMessageSyncSlice");

ChatSendMessageResult decodeChatSendMessageResult(Object? response) =>
    ChatSendMessageResult.fromWire(_requiredObject(response, "ChatSendMessageResult"), "ChatSendMessageResult");

ContactHomePageSlice decodeContactHomePageSlice(Object? response) =>
    ContactHomePageSlice.fromWire(_requiredObject(response, "ContactHomePageSlice"), "ContactHomePageSlice");

ContactPageSlice decodeContactPageSlice(Object? response) =>
    ContactPageSlice.fromWire(_requiredObject(response, "ContactPageSlice"), "ContactPageSlice");

ConversationAssetPage decodeConversationAssetPage(Object? response) =>
    ConversationAssetPage.fromWire(_requiredObject(response, "ConversationAssetPage"), "ConversationAssetPage");

ConversationBatchSlice decodeConversationBatchSlice(Object? response) =>
    ConversationBatchSlice.fromWire(_requiredObject(response, "ConversationBatchSlice"), "ConversationBatchSlice");

ConversationCommandAck decodeConversationCommandAck(Object? response) =>
    ConversationCommandAck.fromWire(_requiredObject(response, "ConversationCommandAck"), "ConversationCommandAck");

ConversationMemberPageSlice decodeConversationMemberPageSlice(Object? response) =>
    ConversationMemberPageSlice.fromWire(_requiredObject(response, "ConversationMemberPageSlice"), "ConversationMemberPageSlice");

ConversationMembershipCommandAck decodeConversationMembershipCommandAck(Object? response) =>
    ConversationMembershipCommandAck.fromWire(_requiredObject(response, "ConversationMembershipCommandAck"), "ConversationMembershipCommandAck");

ConversationPageSlice decodeConversationPageSlice(Object? response) =>
    ConversationPageSlice.fromWire(_requiredObject(response, "ConversationPageSlice"), "ConversationPageSlice");

ConversationTimestampIndexSlice decodeConversationTimestampIndexSlice(Object? response) =>
    ConversationTimestampIndexSlice.fromWire(_requiredObject(response, "ConversationTimestampIndexSlice"), "ConversationTimestampIndexSlice");

ConversationUserStateCommandAck decodeConversationUserStateCommandAck(Object? response) =>
    ConversationUserStateCommandAck.fromWire(_requiredObject(response, "ConversationUserStateCommandAck"), "ConversationUserStateCommandAck");

GatheringChatBoardSlice decodeGatheringChatBoardSlice(Object? response) =>
    GatheringChatBoardSlice.fromWire(_requiredObject(response, "GatheringChatBoardSlice"), "GatheringChatBoardSlice");

GroupCandidatePageSlice decodeGroupCandidatePageSlice(Object? response) =>
    GroupCandidatePageSlice.fromWire(_requiredObject(response, "GroupCandidatePageSlice"), "GroupCandidatePageSlice");

GroupHome decodeGroupHome(Object? response) =>
    GroupHome.fromWire(_requiredObject(response, "GroupHome"), "GroupHome");

MessageCommandAck decodeMessageCommandAck(Object? response) =>
    MessageCommandAck.fromWire(_requiredObject(response, "MessageCommandAck"), "MessageCommandAck");

MessageHomePageSlice decodeMessageHomePageSlice(Object? response) =>
    MessageHomePageSlice.fromWire(_requiredObject(response, "MessageHomePageSlice"), "MessageHomePageSlice");

MessagePageSlice decodeMessagePageSlice(Object? response) =>
    MessagePageSlice.fromWire(_requiredObject(response, "MessagePageSlice"), "MessagePageSlice");

MessageReceiptPageSlice decodeMessageReceiptPageSlice(Object? response) =>
    MessageReceiptPageSlice.fromWire(_requiredObject(response, "MessageReceiptPageSlice"), "MessageReceiptPageSlice");

SelectableGroupContactPageSlice decodeSelectableGroupContactPageSlice(Object? response) =>
    SelectableGroupContactPageSlice.fromWire(_requiredObject(response, "SelectableGroupContactPageSlice"), "SelectableGroupContactPageSlice");

SelectableGroupConversationPageSlice decodeSelectableGroupConversationPageSlice(Object? response) =>
    SelectableGroupConversationPageSlice.fromWire(_requiredObject(response, "SelectableGroupConversationPageSlice"), "SelectableGroupConversationPageSlice");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

double _requiredDouble(Object? value, String path) {
  if (value is! num) throw FormatException('$path must be a number');
  return value.toDouble();
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
