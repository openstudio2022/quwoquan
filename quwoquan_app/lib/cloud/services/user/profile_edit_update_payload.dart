/// 编辑资料页 → [UserProfileRepository.updateProfile] 的强类型载荷（Map 仅在 Repository 边界）。
///
/// 字段与 contracts/metadata/user/user_profile/service.yaml `UpdateUserProfile`
/// 的 `request_fields`（nickname / displayName / bio / avatarUrl / backgroundUrl …）对齐。
/// 采用 PATCH 语义：只有本次实际编辑的字段才非 null 并进入 wire，再用 `fieldsMask`
/// 显式声明更新范围，避免「显式 null / 空串」误清空未改动字段。
class ProfileEditUpdatePayload {
  const ProfileEditUpdatePayload({
    this.nickname,
    this.bio,
    this.avatarUrl,
    this.backgroundUrl,
  });

  /// 昵称（主页展示名）。非空表示本次编辑了昵称。
  final String? nickname;

  /// 个人简介。
  final String? bio;

  /// 头像引用（媒体对象 key 或绝对地址）。
  final String? avatarUrl;

  /// 封面引用（媒体对象 key 或绝对地址）。
  final String? backgroundUrl;

  /// 是否未携带任何可更新字段（用于跳过空保存）。
  bool get isEmpty =>
      nickname == null &&
      bio == null &&
      avatarUrl == null &&
      backgroundUrl == null;

  Map<String, dynamic> toRepositoryMap() {
    final map = <String, dynamic>{};
    final fieldsMask = <String>[];
    final nick = nickname;
    if (nick != null) {
      // 昵称同时回填 displayName，保证主页展示名与列表/评论展示名一致更新。
      map['nickname'] = nick;
      map['displayName'] = nick;
      fieldsMask
        ..add('nickname')
        ..add('displayName');
    }
    final bioValue = bio;
    if (bioValue != null) {
      map['bio'] = bioValue;
      fieldsMask.add('bio');
    }
    final avatar = avatarUrl;
    if (avatar != null) {
      map['avatarUrl'] = avatar;
      fieldsMask.add('avatarUrl');
    }
    final cover = backgroundUrl;
    if (cover != null) {
      map['backgroundUrl'] = cover;
      fieldsMask.add('backgroundUrl');
    }
    map['fieldsMask'] = fieldsMask;
    return map;
  }
}
