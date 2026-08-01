import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 跳转到作者主页时通过 GoRouter extra 传递的初始展示数据。
/// 取代之前散落的 `Map<String, String?>` {'avatar':..., 'displayName':..., 'backgroundImage':...}
class UserProfileRouteExtra {
  const UserProfileRouteExtra({
    this.personaId,
    this.avatar,
    this.displayName,
    this.backgroundImage,
    this.openMessageComposer = false,
    this.greetingIntersectionRef,
  });

  final String? personaId;
  final String? avatar;
  final String? displayName;
  final String? backgroundImage;

  /// 打开主页后立即执行主页既有的「私信 / 打招呼」分流。
  ///
  /// 交集卡的 `dispatch: message` 行动（打招呼 / 私信）用它把承诺兑现到真实破冰
  /// 状态机上，而不是只把用户丢在对方主页；能力位、陌生人破冰、登录续接全部复用
  /// 主页原有实现，不在交集组件内重造第二套私信逻辑。
  final bool openMessageComposer;
  final GreetingIntersectionRef? greetingIntersectionRef;

  /// null / empty 过滤：与路由解析侧保持一致
  String? get safePersonaId => personaId?.isEmpty == true ? null : personaId;
  String? get safeAvatar => avatar?.isEmpty == true ? null : avatar;
  String? get safeDisplayName =>
      displayName?.isEmpty == true ? null : displayName;
  String? get safeBackgroundImage =>
      backgroundImage?.isEmpty == true ? null : backgroundImage;
}
