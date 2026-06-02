import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';

const String loginDismissFallbackQueryParam = 'dismiss_fallback';
const String loginGuestDismissPopQueryParam = 'guest_dismiss_pop';

/// 需要账号身份的 App 动作。每个动作只表达一个事实：「这个动作需要账号身份」。
///
/// 这是「需要登录的功能入口矩阵」的唯一真相源：所有受限入口都映射到这里的
/// 某个 reason，并通过 [requireLogin] 统一拦截，禁止页面各自手写
/// `AppRoutePaths.login(...)` 与提示语。
enum AuthGateReason {
  profileTab,
  createPost,
  openChat,
  sendMessage,
  comment,
  like,
  favorite,
  follow,
  followingFeed,
  shareRecord,
  personaManage,
  settingsAccount,
  mediaUpload,
  report,
  joinCircle,
  addContact,
  startGroupChat,
  createCircle,
  generic,
}

/// 单个受限入口的契约：登录页标题、轻提示、以及它背后调用的需登录 API operation。
///
/// `requiredOperations` 用于与 metadata 生成的 `required` API 鉴权快照做交叉校验，
/// 防止「某个 required API 被 UI 调用却没有登录 gate」的遗漏。
class AuthGateEntry {
  const AuthGateEntry({
    required this.reason,
    required this.title,
    required this.prompt,
    required this.requiredOperations,
  });

  final AuthGateReason reason;
  final String title;
  final String prompt;
  final List<String> requiredOperations;
}

/// 受登录约束的 App 功能入口矩阵（覆盖主导航、内容互动、评论、创作、消息、
/// 用户关系、设置、媒体上传、举报）。
const Map<AuthGateReason, AuthGateEntry> authGateMatrix =
    <AuthGateReason, AuthGateEntry>{
      AuthGateReason.profileTab: AuthGateEntry(
        reason: AuthGateReason.profileTab,
        title: UITextConstants.authGateTitleProfile,
        prompt: UITextConstants.authGatePromptProfile,
        requiredOperations: <String>['GetMeProfile'],
      ),
      AuthGateReason.createPost: AuthGateEntry(
        reason: AuthGateReason.createPost,
        title: UITextConstants.authGateTitleCreate,
        prompt: UITextConstants.authGatePromptCreate,
        requiredOperations: <String>['CreatePost', 'UpdatePost'],
      ),
      AuthGateReason.openChat: AuthGateEntry(
        reason: AuthGateReason.openChat,
        title: UITextConstants.authGateTitleOpenChat,
        prompt: UITextConstants.authGatePromptOpenChat,
        requiredOperations: <String>['ListConversations', 'GetConversation'],
      ),
      AuthGateReason.sendMessage: AuthGateEntry(
        reason: AuthGateReason.sendMessage,
        title: UITextConstants.authGateTitleSendMessage,
        prompt: UITextConstants.authGatePromptSendMessage,
        requiredOperations: <String>['SendMessage'],
      ),
      AuthGateReason.comment: AuthGateEntry(
        reason: AuthGateReason.comment,
        title: UITextConstants.authGateTitleComment,
        prompt: UITextConstants.authGatePromptComment,
        requiredOperations: <String>['CreateComment'],
      ),
      // 点赞已下放为「游客设备态可写」：LikePost 鉴权为 optional + anonymous_policy=allow，
      // 游客按 deviceActorId 维度真实写入、登录用户按账号维度写入，互不并账。
      // 因此点赞不再触发登录门，requiredOperations 留空（保留 reason 以兼容历史调用）。
      AuthGateReason.like: AuthGateEntry(
        reason: AuthGateReason.like,
        title: UITextConstants.authGateTitleLike,
        prompt: UITextConstants.authGatePromptLike,
        requiredOperations: <String>[],
      ),
      AuthGateReason.favorite: AuthGateEntry(
        reason: AuthGateReason.favorite,
        title: UITextConstants.authGateTitleFavorite,
        prompt: UITextConstants.authGatePromptFavorite,
        requiredOperations: <String>['FavoritePost'],
      ),
      AuthGateReason.follow: AuthGateEntry(
        reason: AuthGateReason.follow,
        title: UITextConstants.authGateTitleFollow,
        prompt: UITextConstants.authGatePromptFollow,
        requiredOperations: <String>['FollowUser'],
      ),
      // 关注频道展示「关注的人」的内容流，游客无关注关系，需登录后查看。
      // 关注流走 GetFeed（鉴权快照为 optional），故此处不声明 requiredOperations，
      // 登录约束是产品决策而非 API 强制。
      AuthGateReason.followingFeed: AuthGateEntry(
        reason: AuthGateReason.followingFeed,
        title: UITextConstants.authGateTitleFollowingFeed,
        prompt: UITextConstants.authGatePromptFollowingFeed,
        requiredOperations: <String>[],
      ),
      // 分享/复制链接已下放为「游客设备态可写」：SharePost 鉴权为 optional +
      // anonymous_policy=allow，游客按 deviceActorId 维度真实累加、登录按账号维度累加，
      // 互不并账。因此分享不再触发登录门，requiredOperations 留空。
      AuthGateReason.shareRecord: AuthGateEntry(
        reason: AuthGateReason.shareRecord,
        title: UITextConstants.authGateTitleShare,
        prompt: UITextConstants.authGatePromptShare,
        requiredOperations: <String>[],
      ),
      AuthGateReason.personaManage: AuthGateEntry(
        reason: AuthGateReason.personaManage,
        title: UITextConstants.authGateTitlePersona,
        prompt: UITextConstants.authGatePromptPersona,
        requiredOperations: <String>['ListPersonas', 'CreatePersona'],
      ),
      AuthGateReason.settingsAccount: AuthGateEntry(
        reason: AuthGateReason.settingsAccount,
        title: UITextConstants.authGateTitleSettingsAccount,
        prompt: UITextConstants.authGatePromptSettingsAccount,
        requiredOperations: <String>['ListCredentials'],
      ),
      AuthGateReason.mediaUpload: AuthGateEntry(
        reason: AuthGateReason.mediaUpload,
        title: UITextConstants.authGateTitleMediaUpload,
        prompt: UITextConstants.authGatePromptMediaUpload,
        requiredOperations: <String>['CreatePost'],
      ),
      AuthGateReason.report: AuthGateEntry(
        reason: AuthGateReason.report,
        title: UITextConstants.authGateTitleReport,
        prompt: UITextConstants.authGatePromptReport,
        requiredOperations: <String>['CreateReport'],
      ),
      AuthGateReason.joinCircle: AuthGateEntry(
        reason: AuthGateReason.joinCircle,
        title: UITextConstants.authGateTitleJoinCircle,
        prompt: UITextConstants.authGatePromptJoinCircle,
        requiredOperations: <String>['JoinCircle'],
      ),
      // 加好友 / 发起群聊 / 建圈子 属「先开面板、动作再登录」的产品级动作门，
      // 登录约束是产品决策而非单一 required API，故 requiredOperations 留空。
      AuthGateReason.addContact: AuthGateEntry(
        reason: AuthGateReason.addContact,
        title: UITextConstants.authGateTitleAddContact,
        prompt: UITextConstants.authGatePromptAddContact,
        requiredOperations: <String>[],
      ),
      AuthGateReason.startGroupChat: AuthGateEntry(
        reason: AuthGateReason.startGroupChat,
        title: UITextConstants.authGateTitleStartGroupChat,
        prompt: UITextConstants.authGatePromptStartGroupChat,
        requiredOperations: <String>[],
      ),
      AuthGateReason.createCircle: AuthGateEntry(
        reason: AuthGateReason.createCircle,
        title: UITextConstants.authGateTitleCreateCircle,
        prompt: UITextConstants.authGatePromptCreateCircle,
        requiredOperations: <String>[],
      ),
      AuthGateReason.generic: AuthGateEntry(
        reason: AuthGateReason.generic,
        title: UITextConstants.authGateTitleGeneric,
        prompt: UITextConstants.authGatePromptGeneric,
        requiredOperations: <String>[],
      ),
    };

extension AuthGateReasonX on AuthGateReason {
  AuthGateEntry get entry => authGateMatrix[this] ?? authGateMatrix[AuthGateReason.generic]!;
  String get title => entry.title;
  String get prompt => entry.prompt;
  List<String> get requiredOperations => entry.requiredOperations;
}

/// 受限「直达路由」守卫的唯一真相源：把路由位置映射到对应的 [AuthGateReason]，
/// 返回 `null` 表示该位置游客可浏览、不得整页拦截。
///
/// 与 [authGateMatrix] 配合，覆盖底栏入口之外的深链。务必保证「我的」tab
/// （/profile 本体）可被游客浏览：MyProfilePage 在未登录时渲染占位页 + 内嵌
/// 登录按钮。一旦整页拦截 /profile，登录页关闭 / 稍后登录会原路返回到 /profile
/// 再次被守卫拦截，形成「关闭→又弹登录」的死循环。
///
/// 注意：`/following` 只是首页内部频道状态，不是可直达的真实受限页面。
/// 若把它误接到路由级守卫，登录页关闭后极易再次命中守卫形成回环。
AuthGateReason? requiredRouteGateForLocation(String loc) {
  if (loc == AppRoutePaths.profile) {
    return null;
  }
  if (loc.startsWith('/profile/')) {
    return AuthGateReason.personaManage;
  }
  if (loc == AppRoutePaths.createEntry || loc.startsWith('/create')) {
    return AuthGateReason.createPost;
  }
  if (loc == AppRoutePaths.chat || loc.startsWith('/chat/')) {
    return AuthGateReason.openChat;
  }
  return null;
}

String buildLoginRouteLocation({
  required String reasonName,
  String? redirect,
  String? dismissFallback,
  bool allowGuestDismissPop = true,
}) {
  final query = <String, String>{
    if (_trimmedOrNull(reasonName) case final value?) 'reason': value,
    if (_trimmedOrNull(redirect) case final value?) 'redirect': value,
    if (_trimmedOrNull(dismissFallback) case final value?)
      loginDismissFallbackQueryParam: value,
    loginGuestDismissPopQueryParam: allowGuestDismissPop ? '1' : '0',
  };
  return Uri(
    path: AppRoutePaths.loginPathTemplate,
    queryParameters: query,
  ).toString();
}

bool loginGuestDismissCanPopFromQuery(String? raw) => raw != '0';

String currentLoginDismissFallback(BuildContext context) {
  try {
    final location = GoRouterState.of(context).uri.toString().trim();
    return location.isEmpty ? AppRoutePaths.home : location;
  } catch (_) {
    return AppRoutePaths.home;
  }
}

String safeLoginDismissFallback({
  String? redirect,
  String? dismissFallback,
}) {
  if (_trimmedOrNull(dismissFallback) case final explicit?) {
    return _normalizedGuestDismissFallback(explicit);
  }
  if (_trimmedOrNull(redirect) case final target?) {
    return _normalizedGuestDismissFallback(target);
  }
  return AppRoutePaths.home;
}

void openLoginPage(
  BuildContext context, {
  required String reasonName,
  String? redirect,
  String? dismissFallback,
  bool allowGuestDismissPop = true,
  bool replace = false,
}) {
  final location = buildLoginRouteLocation(
    reasonName: reasonName,
    redirect: redirect,
    dismissFallback: dismissFallback,
    allowGuestDismissPop: allowGuestDismissPop,
  );
  if (replace) {
    context.go(location);
  } else {
    context.push(location);
  }
}

/// 解析登录页标题：优先用 AuthGateReason，其次回退到 [AuthPromptReason]。
String? authGateTitleForReasonName(String? name) {
  if (name == null || name.isEmpty) {
    return null;
  }
  for (final reason in AuthGateReason.values) {
    if (reason.name == name) {
      return reason.title;
    }
  }
  return null;
}

/// 统一登录拦截器：所有受限入口都应调用本方法，不要各自拼 login 路由与提示语。
///
/// 行为：
/// - 已登录：直接返回 `true`，调用方继续执行原动作。
/// - 未登录：先在原页面给一句短提示，再进入全屏登录页；返回 `false`。
///   登录成功后由登录页负责回源（`redirect` 非空回 redirect，否则 pop 回原页）。
///
/// 防抖：同一 reason 在 [_debounceWindow] 内重复触发只提示一次、只 push 一次登录页。
class AuthGate {
  AuthGate._();

  static const Duration _debounceWindow = Duration(milliseconds: 800);
  static final Map<AuthGateReason, DateTime> _lastTriggered =
      <AuthGateReason, DateTime>{};

  @visibleForTesting
  static void resetDebounce() => _lastTriggered.clear();

  static bool _isDebounced(AuthGateReason reason) {
    final now = DateTime.now();
    final last = _lastTriggered[reason];
    if (last != null && now.difference(last) < _debounceWindow) {
      return true;
    }
    _lastTriggered[reason] = now;
    return false;
  }

  static bool isAuthenticated(WidgetRef ref) =>
      ref.read(authSessionControllerProvider).isAuthenticated;
}

/// 「游客设备态可写」动作：点赞 / 分享。这些动作不再触发登录门——游客以
/// deviceActorId 设备维度真实写入、登录用户以账号维度写入，云侧独立计数不并账
/// （详见 service.yaml LikePost/SharePost = optional + anonymous_policy:allow）。
///
/// 收口为单一真相源：所有 like/share 入口都通过 [requireLogin] / [runWhenLoggedIn]
/// 统一放行，无需逐个改调用点，避免遗漏导致游客被错误拦截。
const Set<AuthGateReason> guestWritableAuthGateReasons = <AuthGateReason>{
  AuthGateReason.like,
  AuthGateReason.shareRecord,
};

/// 拦截受限动作。返回 `true` 表示可继续（已登录或属游客设备态可写动作），
/// `false` 表示已引导登录、调用方应停止。
Future<bool> requireLogin(
  WidgetRef ref,
  BuildContext context,
  AuthGateReason reason, {
  String? redirect,
  String? dismissFallback,
  bool allowGuestDismissPop = true,
}) async {
  // 游客设备态可写动作（点赞/分享）：游客与登录用户都直接放行，乐观态与 outbox
  // 写入由调用方完成，设备维度计数由云侧依据 X-Client-Device-Actor-Id 实现。
  if (guestWritableAuthGateReasons.contains(reason)) {
    return true;
  }
  if (AuthGate.isAuthenticated(ref)) {
    return true;
  }
  if (AuthGate._isDebounced(reason)) {
    return false;
  }
  AppToast.show(context, reason.prompt);
  if (!context.mounted) {
    return false;
  }
  openLoginPage(
    context,
    reasonName: reason.name,
    redirect: redirect,
    dismissFallback: dismissFallback ?? currentLoginDismissFallback(context),
    allowGuestDismissPop: allowGuestDismissPop,
  );
  return false;
}

/// 受限动作的 fire-and-forget 包装：给 `void` 回调（如 onTap）使用。
///
/// 已登录则执行 [action]；未登录则按 [requireLogin] 引导登录，并**不执行**动作。
/// 这样各写动作入口无需把 `void` 回调改成 `Future`，调用方签名保持不变。
void runWhenLoggedIn(
  WidgetRef ref,
  BuildContext context,
  AuthGateReason reason,
  FutureOr<void> Function() action, {
  String? redirect,
  String? dismissFallback,
  bool allowGuestDismissPop = true,
}) {
  unawaited(() async {
    final allowed = await requireLogin(
      ref,
      context,
      reason,
      redirect: redirect,
      dismissFallback: dismissFallback,
      allowGuestDismissPop: allowGuestDismissPop,
    );
    if (!allowed || !context.mounted) {
      return;
    }
    await action();
  }());
}

String _pathFromLocation(String location) {
  final parsed = Uri.tryParse(location);
  final path = parsed?.path.trim() ?? location.trim();
  return path.isEmpty ? AppRoutePaths.home : path;
}

String? _trimmedOrNull(String? value) {
  final trimmed = value?.trim() ?? '';
  return trimmed.isEmpty ? null : trimmed;
}

String _normalizedGuestDismissFallback(String location) {
  final path = _pathFromLocation(location);
  if (path == AppRoutePaths.profile || path.startsWith('/profile/')) {
    return AppRoutePaths.profile;
  }
  if (requiredRouteGateForLocation(path) != null) {
    return AppRoutePaths.home;
  }
  // `/following` 属于首页内部频道，不是可直达路由；游客关闭登录后回首页。
  if (path == '/following') {
    return AppRoutePaths.home;
  }
  final parsed = Uri.tryParse(location);
  if (parsed == null) {
    return path;
  }
  return parsed.toString();
}
