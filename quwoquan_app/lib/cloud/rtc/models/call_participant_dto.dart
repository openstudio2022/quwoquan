class CallParticipantDto {
  final String userId;
  final String role;
  final String status;
  final bool isMuted;
  final bool isCameraOn;
  final DateTime? joinedAt;
  final DateTime? leftAt;

  const CallParticipantDto({
    required this.userId,
    required this.role,
    required this.status,
    this.isMuted = false,
    this.isCameraOn = true,
    this.joinedAt,
    this.leftAt,
  });

  factory CallParticipantDto.fromMap(Map<String, dynamic> map) {
    return CallParticipantDto(
      userId: map['userId'] as String? ?? '',
      role: map['role'] as String? ?? 'invitee',
      status: map['status'] as String? ?? 'invited',
      isMuted: map['isMuted'] as bool? ?? false,
      isCameraOn: map['isCameraOn'] as bool? ?? true,
      joinedAt: map['joinedAt'] != null
          ? DateTime.tryParse(map['joinedAt'] as String)
          : null,
      leftAt: map['leftAt'] != null
          ? DateTime.tryParse(map['leftAt'] as String)
          : null,
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'userId': userId,
      'role': role,
      'status': status,
      'isMuted': isMuted,
      'isCameraOn': isCameraOn,
      if (joinedAt != null) 'joinedAt': joinedAt!.toIso8601String(),
      if (leftAt != null) 'leftAt': leftAt!.toIso8601String(),
    };
  }

  CallParticipantDto copyWith({
    String? userId,
    String? role,
    String? status,
    bool? isMuted,
    bool? isCameraOn,
    DateTime? joinedAt,
    DateTime? leftAt,
  }) {
    return CallParticipantDto(
      userId: userId ?? this.userId,
      role: role ?? this.role,
      status: status ?? this.status,
      isMuted: isMuted ?? this.isMuted,
      isCameraOn: isCameraOn ?? this.isCameraOn,
      joinedAt: joinedAt ?? this.joinedAt,
      leftAt: leftAt ?? this.leftAt,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallParticipantDto &&
          runtimeType == other.runtimeType &&
          userId == other.userId &&
          role == other.role &&
          status == other.status &&
          isMuted == other.isMuted &&
          isCameraOn == other.isCameraOn &&
          joinedAt == other.joinedAt &&
          leftAt == other.leftAt;

  @override
  int get hashCode => Object.hash(
        userId,
        role,
        status,
        isMuted,
        isCameraOn,
        joinedAt,
        leftAt,
      );
}
