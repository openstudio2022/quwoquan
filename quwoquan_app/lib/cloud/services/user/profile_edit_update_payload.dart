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
    this.avatarAssetId,
    this.avatarUrl,
    this.backgroundAssetId,
    this.backgroundUrl,
    this.gender,
    this.birthDate,
    this.regionTagRef,
    this.occupationTagRef,
    this.interestTagRefs,
  });

  /// 昵称（主页展示名）。非空表示本次编辑了昵称。
  final String? nickname;

  /// 个人简介。
  final String? bio;

  /// 头像媒体资产 ID。保存前通过 profile media upload 得到。
  final String? avatarAssetId;

  /// 头像展示 URL。仅作为服务返回/上传完成后的展示辅助，不写入本地路径。
  final String? avatarUrl;

  /// 封面媒体资产 ID。保存前通过 profile media upload 得到。
  final String? backgroundAssetId;

  /// 封面展示 URL。仅作为服务返回/上传完成后的展示辅助，不写入本地路径。
  final String? backgroundUrl;

  /// 性别枚举：male / female / other / unspecified。
  final String? gender;

  /// 生日，自然日期 `YYYY-MM-DD`，不携带时区。
  final String? birthDate;

  /// 省市两级行政区 tagRef，公开显示值由服务端派生。
  final String? regionTagRef;

  /// 职业 tagRef，系统标签体系单选。
  final String? occupationTagRef;

  /// 兴趣 tagRefs，系统标签体系多选。
  final List<String>? interestTagRefs;

  /// 是否未携带任何可更新字段（用于跳过空保存）。
  bool get isEmpty =>
      nickname == null &&
      bio == null &&
      avatarAssetId == null &&
      avatarUrl == null &&
      backgroundAssetId == null &&
      backgroundUrl == null &&
      gender == null &&
      birthDate == null &&
      regionTagRef == null &&
      occupationTagRef == null &&
      interestTagRefs == null;

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
    final avatarAsset = avatarAssetId;
    if (avatarAsset != null) {
      map['avatarAssetId'] = avatarAsset;
      fieldsMask.add('avatarAssetId');
    }
    final avatar = avatarUrl;
    if (avatar != null) {
      map['avatarUrl'] = avatar;
      fieldsMask.add('avatarUrl');
    }
    final coverAsset = backgroundAssetId;
    if (coverAsset != null) {
      map['backgroundAssetId'] = coverAsset;
      fieldsMask.add('backgroundAssetId');
    }
    final cover = backgroundUrl;
    if (cover != null) {
      map['backgroundUrl'] = cover;
      fieldsMask.add('backgroundUrl');
    }
    final genderValue = gender;
    if (genderValue != null) {
      map['gender'] = genderValue;
      fieldsMask.add('gender');
    }
    final birthdayValue = birthDate;
    if (birthdayValue != null) {
      map['birthDate'] = birthdayValue;
      fieldsMask.add('birthDate');
    }
    final regionTagRefValue = regionTagRef;
    if (regionTagRefValue != null) {
      map['regionTagRef'] = regionTagRefValue;
      fieldsMask.add('regionTagRef');
    }
    final occupationValue = occupationTagRef;
    final interestsValue = interestTagRefs;
    if (occupationValue != null || interestsValue != null) {
      final normalizedInterests = interestsValue
          ?.where((tag) => tag.trim().isNotEmpty)
          .map((tag) => tag.trim())
          .toList(growable: false);
      if (occupationValue != null) {
        map['occupationTagRef'] = occupationValue;
        fieldsMask.add('occupationTagRef');
      }
      if (normalizedInterests != null) {
        map['interestTagRefs'] = normalizedInterests;
        fieldsMask.add('interestTagRefs');
      }
      final identityTags = <String>[
        if (occupationValue != null && occupationValue.trim().isNotEmpty)
          occupationValue.trim(),
        ...?normalizedInterests,
      ];
      map['identityTags'] = identityTags;
      fieldsMask.add('identityTags');
    }
    map['fieldsMask'] = fieldsMask;
    return map;
  }
}
