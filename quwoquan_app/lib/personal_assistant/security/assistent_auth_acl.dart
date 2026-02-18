class AssistentAccessContext {
  const AssistentAccessContext({
    required this.channel,
    required this.actorId,
    required this.resource,
    required this.action,
  });

  final String channel;
  final String actorId;
  final String resource;
  final String action;
}

class AssistentAuthAcl {
  const AssistentAuthAcl();

  bool allow(AssistentAccessContext context) {
    if (context.actorId.trim().isEmpty) return false;
    if (context.resource.trim().isEmpty) return false;
    if (context.action.trim().isEmpty) return false;
    return true;
  }
}

