/// Visible activity category on a Persona profile's interaction surface.
enum InteractionSubTab { likes, comments, shares }

/// Direction of profile interaction activity relative to the viewed Persona.
enum InteractionDirection { received, sent }

extension InteractionSubTabMetadata on InteractionSubTab {
  String get id => switch (this) {
    InteractionSubTab.likes => 'likes',
    InteractionSubTab.comments => 'comments',
    InteractionSubTab.shares => 'shares',
  };
}

InteractionSubTab interactionSubTabFromId(String id) {
  return switch (id) {
    'comments' => InteractionSubTab.comments,
    'shares' => InteractionSubTab.shares,
    _ => InteractionSubTab.likes,
  };
}
