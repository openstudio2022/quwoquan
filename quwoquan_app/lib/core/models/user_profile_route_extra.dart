/// 跳转到作者主页时通过 GoRouter extra 传递的初始展示数据。
/// 取代之前散落的 `Map<String, String?>` {'avatar':..., 'displayName':..., 'backgroundImage':...}
class UserProfileRouteExtra {
  const UserProfileRouteExtra({
    this.subAccountId,
    this.avatar,
    this.displayName,
    this.backgroundImage,
  });

  final String? subAccountId;
  final String? avatar;
  final String? displayName;
  final String? backgroundImage;

  /// null / empty 过滤：与路由解析侧保持一致
  String? get safeSubAccountId =>
      subAccountId?.isEmpty == true ? null : subAccountId;
  String? get safeAvatar => avatar?.isEmpty == true ? null : avatar;
  String? get safeDisplayName => displayName?.isEmpty == true ? null : displayName;
  String? get safeBackgroundImage =>
      backgroundImage?.isEmpty == true ? null : backgroundImage;
}
