/// 编辑资料页 → [UserProfileRepository.updateProfile] 的强类型载荷（Map 仅在 Repository 边界）。
class ProfileEditUpdatePayload {
  const ProfileEditUpdatePayload({
    required this.nickname,
    required this.username,
    required this.bio,
    this.website = '',
  });

  final String nickname;
  final String username;
  final String bio;
  final String website;

  Map<String, dynamic> toRepositoryMap() => <String, dynamic>{
    'nickname': nickname,
    'username': username,
    'bio': bio,
    'website': website,
  };
}
