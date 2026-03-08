enum CallStatus {
  initiated,
  ringing,
  connecting,
  inCall,
  ended;

  static CallStatus fromString(String value) {
    return switch (value) {
      'initiated' => CallStatus.initiated,
      'ringing' => CallStatus.ringing,
      'connecting' => CallStatus.connecting,
      'in_call' => CallStatus.inCall,
      'ended' => CallStatus.ended,
      _ => CallStatus.initiated,
    };
  }

  String toApiString() {
    return switch (this) {
      CallStatus.initiated => 'initiated',
      CallStatus.ringing => 'ringing',
      CallStatus.connecting => 'connecting',
      CallStatus.inCall => 'in_call',
      CallStatus.ended => 'ended',
    };
  }

  bool get isActive =>
      this == CallStatus.initiated ||
      this == CallStatus.ringing ||
      this == CallStatus.connecting ||
      this == CallStatus.inCall;
}

enum CallType {
  audio,
  video;

  static CallType fromString(String value) {
    return switch (value) {
      'video' => CallType.video,
      _ => CallType.audio,
    };
  }

  String toApiString() => name;

  bool get isVideo => this == CallType.video;
  bool get isAudio => this == CallType.audio;
}

enum EndReason {
  completed,
  cancelled,
  rejected,
  timeout,
  busy,
  initiatorHangup,
  networkError,
  unknown;

  static EndReason fromString(String? value) {
    return switch (value) {
      'completed' => EndReason.completed,
      'cancelled' => EndReason.cancelled,
      'rejected' => EndReason.rejected,
      'timeout' => EndReason.timeout,
      'busy' => EndReason.busy,
      'initiator_hangup' => EndReason.initiatorHangup,
      'network_error' => EndReason.networkError,
      _ => EndReason.unknown,
    };
  }
}

enum ParticipantRole {
  initiator,
  invitee;

  static ParticipantRole fromString(String value) {
    return switch (value) {
      'initiator' => ParticipantRole.initiator,
      _ => ParticipantRole.invitee,
    };
  }
}

enum ParticipantStatus {
  invited,
  ringing,
  connecting,
  connected,
  left,
  timeout;

  static ParticipantStatus fromString(String value) {
    return switch (value) {
      'invited' => ParticipantStatus.invited,
      'ringing' => ParticipantStatus.ringing,
      'connecting' => ParticipantStatus.connecting,
      'connected' => ParticipantStatus.connected,
      'left' => ParticipantStatus.left,
      'timeout' => ParticipantStatus.timeout,
      _ => ParticipantStatus.invited,
    };
  }

  bool get isActive =>
      this == ParticipantStatus.connecting ||
      this == ParticipantStatus.connected;
}
