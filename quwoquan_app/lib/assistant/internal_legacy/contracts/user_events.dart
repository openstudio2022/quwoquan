enum UserEventType {
  processReplace,
  processAppend,
  processCommit,
  answerDelta,
  unknown,
}

enum UserEventScope { root, skill, aggregation, unknown }

class UserEvent {
  const UserEvent({
    required this.type,
    required this.scope,
    this.message = '',
    this.nodeId = '',
    this.runId = '',
    this.payload = const <String, dynamic>{},
  });

  final UserEventType type;
  final UserEventScope scope;
  final String message;
  final String nodeId;
  final String runId;
  final Map<String, dynamic> payload;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'type': _typeToWire(type),
    'scope': _scopeToWire(scope),
    'message': message,
    'nodeId': nodeId,
    'runId': runId,
    'payload': payload,
  };

  factory UserEvent.fromJson(Map<String, dynamic> json) {
    return UserEvent(
      type: _typeFromWire((json['type'] as String?)?.trim() ?? ''),
      scope: _scopeFromWire((json['scope'] as String?)?.trim() ?? ''),
      message: (json['message'] as String?)?.trim() ?? '',
      nodeId: (json['nodeId'] as String?)?.trim() ?? '',
      runId: (json['runId'] as String?)?.trim() ?? '',
      payload:
          (json['payload'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{},
    );
  }

  static UserEventType _typeFromWire(String raw) {
    switch (raw) {
      case 'process_replace':
        return UserEventType.processReplace;
      case 'process_append':
        return UserEventType.processAppend;
      case 'process_commit':
        return UserEventType.processCommit;
      case 'answer_delta':
        return UserEventType.answerDelta;
      default:
        return UserEventType.unknown;
    }
  }

  static String _typeToWire(UserEventType type) {
    switch (type) {
      case UserEventType.processReplace:
        return 'process_replace';
      case UserEventType.processAppend:
        return 'process_append';
      case UserEventType.processCommit:
        return 'process_commit';
      case UserEventType.answerDelta:
        return 'answer_delta';
      case UserEventType.unknown:
        return 'unknown';
    }
  }

  static UserEventScope _scopeFromWire(String raw) {
    switch (raw) {
      case 'root':
        return UserEventScope.root;
      case 'skill':
        return UserEventScope.skill;
      case 'aggregation':
        return UserEventScope.aggregation;
      default:
        return UserEventScope.unknown;
    }
  }

  static String _scopeToWire(UserEventScope scope) {
    switch (scope) {
      case UserEventScope.root:
        return 'root';
      case UserEventScope.skill:
        return 'skill';
      case UserEventScope.aggregation:
        return 'aggregation';
      case UserEventScope.unknown:
        return 'unknown';
    }
  }
}
