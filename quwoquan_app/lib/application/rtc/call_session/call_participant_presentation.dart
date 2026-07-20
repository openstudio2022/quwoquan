final class CallParticipantPresentation {
  const CallParticipantPresentation({
    required this.userId,
    required this.displayName,
    this.avatarUrl,
    required this.knownInCurrentContext,
  });

  final String userId;
  final String displayName;
  final String? avatarUrl;
  final bool knownInCurrentContext;
}

/// CallSession 只持有参与状态；展示资料由端侧通过当前会话成员投影组合。
abstract interface class CallParticipantPresentationResolver {
  Future<Map<String, CallParticipantPresentation>> resolve({
    required String conversationId,
    required Set<String> userIds,
  });
}
