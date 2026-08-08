import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

enum AppForwardSubjectKind {
  profileQr,
  contentPost,
  userProfile,
  entityProfile,
  circle,
}

extension AppForwardSubjectKindWire on AppForwardSubjectKind {
  String get wire => switch (this) {
    AppForwardSubjectKind.profileQr => 'profile_qr',
    AppForwardSubjectKind.contentPost => 'content_post',
    AppForwardSubjectKind.userProfile => 'user_profile',
    AppForwardSubjectKind.entityProfile => 'entity_profile',
    AppForwardSubjectKind.circle => 'circle',
  };
}

enum AppForwardRecipientKind { conversation, user, group }

abstract final class AppForwardLimits {
  static const int recentRecipients = 10;
}

class AppForwardPayload {
  const AppForwardPayload({
    required this.kind,
    required this.title,
    this.subtitle = '',
    this.thumbnailUrl = '',
    this.deeplink = '',
    this.landingUrl = '',
    this.shareText = '',
    this.previewBuilder,
    this.extra = const <String, Object?>{},
    this.objectRef,
  });

  final AppForwardSubjectKind kind;
  final String title;
  final String subtitle;
  final String thumbnailUrl;
  final String deeplink;
  final String landingUrl;
  final String shareText;
  final WidgetBuilder? previewBuilder;
  final Map<String, Object?> extra;
  final MessageCardObjectRef? objectRef;

  String get messagePreview {
    final explicit = shareText.trim();
    if (explicit.isNotEmpty) {
      return explicit;
    }
    return title.trim();
  }

  MessageCard toMessageCardCommand({String message = ''}) {
    return MessageCard(
      kind: MessageCardKind.fromWire(kind.wire, 'AppForwardPayload.kind'),
      title: title,
      objectRef: objectRef,
      subtitle: subtitle,
      thumbnailUrl: thumbnailUrl,
      deeplink: deeplink,
      landingUrl: landingUrl,
      shareText: shareText,
      message: message,
      attributes: extra.entries
          .where(
            (entry) =>
                entry.key.trim().isNotEmpty &&
                entry.value != null &&
                entry.value.toString().trim().isNotEmpty,
          )
          .map(
            (entry) => MessageCardAttribute(
              name: entry.key,
              value: entry.value.toString(),
            ),
          )
          .toList(growable: false),
    );
  }
}

class AppForwardRecipient {
  const AppForwardRecipient({
    required this.id,
    required this.kind,
    required this.title,
    this.subtitle = '',
    this.avatarUrl = '',
    this.conversationId = '',
    this.userId = '',
    this.memberCount = 0,
    this.lastActiveAt,
  });

  final String id;
  final AppForwardRecipientKind kind;
  final String title;
  final String subtitle;
  final String avatarUrl;
  final String conversationId;
  final String userId;
  final int memberCount;
  final DateTime? lastActiveAt;

  bool get canSend =>
      conversationId.trim().isNotEmpty || userId.trim().isNotEmpty;

  String get displaySubtitle {
    final explicit = subtitle.trim();
    if (explicit.isNotEmpty) {
      return explicit;
    }
    if (memberCount > 0) {
      return ChatText.forwardRecipientGroupMemberCount(memberCount);
    }
    return '';
  }
}

List<AppForwardRecipient> sortForwardRecipientsByRecent(
  Iterable<AppForwardRecipient> recipients,
) {
  final out = recipients.where((recipient) => recipient.canSend).toList();
  out.sort((a, b) {
    final at = a.lastActiveAt?.millisecondsSinceEpoch ?? 0;
    final bt = b.lastActiveAt?.millisecondsSinceEpoch ?? 0;
    if (at != bt) {
      return bt.compareTo(at);
    }
    return a.title.compareTo(b.title);
  });
  return out;
}

List<AppForwardRecipient> uniqueForwardRecipients(
  Iterable<AppForwardRecipient> recipients,
) {
  final seen = <String>{};
  final out = <AppForwardRecipient>[];
  for (final recipient in recipients) {
    final key = recipient.conversationId.trim().isNotEmpty
        ? 'conversation:${recipient.conversationId.trim()}'
        : 'user:${recipient.userId.trim()}';
    if (key == 'user:' || !seen.add(key)) {
      continue;
    }
    out.add(recipient);
  }
  return out;
}
