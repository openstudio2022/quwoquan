/// 已由 Persona 查询确认的端侧公开资料快照。
///
/// 该类型只暴露跨页面实际消费的强类型字段；传输层 metadata 不进入应用边界。
final class PersonaProfileSnapshot {
  const PersonaProfileSnapshot({
    required this.personaId,
    required this.ownerUserId,
    this.userHandle,
    this.avatarUrl,
    this.bio,
    this.displayName,
    this.backgroundImage,
  });

  final String personaId;
  final String ownerUserId;
  final String? userHandle;
  final String? avatarUrl;
  final String? bio;
  final String? displayName;
  final String? backgroundImage;
}
