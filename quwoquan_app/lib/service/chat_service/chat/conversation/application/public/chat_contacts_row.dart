enum ChatContactsRowKind { user, circle, group }

/// Typed ContactHome row consumed by conversation and inbox composition.
final class ChatContactsRow {
  const ChatContactsRow({
    required this.kind,
    required this.id,
    required this.displayName,
    required this.avatarUrl,
    required this.subtitle,
    this.personaId,
    this.userHandle,
    this.relationState = 'not_following',
    this.source = '',
    this.isStarred = false,
    this.circleId,
    this.conversationId,
  });

  final ChatContactsRowKind kind;
  final String id;
  final String displayName;
  final String avatarUrl;
  final String subtitle;
  final String? personaId;
  final String? userHandle;
  final String relationState;
  final String source;
  final bool isStarred;
  final String? circleId;
  final String? conversationId;

  bool get isMutualFollow => relationState == 'mutual';
}
