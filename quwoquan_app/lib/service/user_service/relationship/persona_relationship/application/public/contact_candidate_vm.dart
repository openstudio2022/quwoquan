/// 添加联系人候选行的「添加」按钮态，由关系能力位驱动（不在 UI 自枚举 relationState）。
enum ContactAddState {
  /// 可添加（not_following）→ 显示「添加」。
  canAdd,

  /// 对方已关注我（followed_by）→ 显示「回关」。
  canFollowBack,

  /// 已是关注/互关（following | mutual）→ 显示「已添加」。
  added,

  /// 本人 → 不展示添加动作。
  isSelf,

  /// 当前 capability 不允许关注；保留候选但禁用动作，不泄露屏蔽原因。
  unavailable,
}

extension ContactAddStateX on ContactAddState {
  bool get canTriggerAdd =>
      this == ContactAddState.canAdd || this == ContactAddState.canFollowBack;
}

/// 添加联系人候选的统一视图模型：搜索结果、手机通讯录匹配、扫码落地都收敛到此，
/// 供确认页与候选行复用（R31 改一处验三面：搜索/通讯录/扫码同源渲染）。
class ContactCandidateVm {
  const ContactCandidateVm({
    required this.personaId,
    required this.displayName,
    required this.userHandle,
    this.avatarUrl,
    this.avatarVersion = 0,
    this.region,
    this.subtitle,
    this.addState = ContactAddState.canAdd,
  });

  final String personaId;
  final String displayName;
  final String userHandle;
  final String? avatarUrl;
  final int avatarVersion;
  final String? region;

  /// 行副标题：通讯录里是「本机联系人姓名」，搜索/扫码里是「趣我圈号」。
  final String? subtitle;
  final ContactAddState addState;

  ContactCandidateVm copyWith({ContactAddState? addState}) {
    return ContactCandidateVm(
      personaId: personaId,
      displayName: displayName,
      userHandle: userHandle,
      avatarUrl: avatarUrl,
      avatarVersion: avatarVersion,
      region: region,
      subtitle: subtitle,
      addState: addState ?? this.addState,
    );
  }

  /// 由关系能力位（relationState + canFollow/canUnfollow）派生「添加」按钮态。
  static ContactAddState addStateFromCapability({
    required String relationState,
    required bool canFollow,
    required bool canUnfollow,
    bool isBlocked = false,
    bool isBlockedBy = false,
  }) {
    if (isBlocked || isBlockedBy) {
      return ContactAddState.unavailable;
    }
    switch (relationState) {
      case 'self':
        return ContactAddState.isSelf;
      case 'following':
      case 'mutual':
        return ContactAddState.added;
      case 'followed_by':
        return canFollow
            ? ContactAddState.canFollowBack
            : ContactAddState.unavailable;
      case 'not_following':
      default:
        // 关系态缺省时回退到能力位：仍可关注 → 可添加。
        if (canUnfollow && !canFollow) {
          return ContactAddState.added;
        }
        return canFollow ? ContactAddState.canAdd : ContactAddState.unavailable;
    }
  }
}
