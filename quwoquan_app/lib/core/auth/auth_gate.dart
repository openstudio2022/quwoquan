import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/auth/auth_continuation.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
  greet,
  comment,
  like,
  wishlist,
  follow,
  followingFeed,
  share,
  personaManage,
  settingsAccount,
  mediaUpload,
  deletePost,
  report,
  blockUser,
  homepageWrite,
  joinCircle,
  addContact,
  startGroupChat,
  createCircle,
  startCall,
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
    required this.subtitle,
    required this.prompt,
    required this.requiredOperations,
  });

  final AuthGateReason reason;
  final String title;
  final String subtitle;
  final String prompt;
  final List<String> requiredOperations;
}

enum LoginReasonCopySource { localApp, localSession, cloudHint }

class LoginReasonCopy {
  const LoginReasonCopy({
    required this.title,
    required this.subtitle,
    required this.source,
  });

  final String title;
  final String subtitle;
  final LoginReasonCopySource source;
}

/// 受登录约束的 App 功能入口矩阵（覆盖主导航、内容互动、评论、创作、消息、
/// 用户关系、设置、媒体上传、举报）。
const Map<AuthGateReason, AuthGateEntry>
authGateMatrix = <AuthGateReason, AuthGateEntry>{
  AuthGateReason.profileTab: AuthGateEntry(
    reason: AuthGateReason.profileTab,
    title: UITextConstants.authGateTitleProfile,
    subtitle: UITextConstants.authGateSubtitleProfile,
    prompt: UITextConstants.authGatePromptProfile,
    // 个人页读取契约允许游客查看其他公开资料；「我的」tab 的登录门是产品
    // 导航决策，不得错误绑定 optional 的 GetSubAccountProfile operation。
    requiredOperations: <String>[],
  ),
  AuthGateReason.createPost: AuthGateEntry(
    reason: AuthGateReason.createPost,
    title: UITextConstants.authGateTitleCreate,
    subtitle: UITextConstants.authGateSubtitleCreate,
    prompt: UITextConstants.authGatePromptCreate,
    requiredOperations: <String>[
      AppCloudOperationIds.contentPostSubmitPostPublication,
    ],
  ),
  AuthGateReason.openChat: AuthGateEntry(
    reason: AuthGateReason.openChat,
    title: ChatText.authGateTitleOpenChat,
    subtitle: ChatText.authGateSubtitleOpenChat,
    prompt: ChatText.authGatePromptOpenChat,
    requiredOperations: <String>[
      AppCloudOperationIds.chatConversationListConversations,
      AppCloudOperationIds.chatConversationGetConversation,
    ],
  ),
  AuthGateReason.sendMessage: AuthGateEntry(
    reason: AuthGateReason.sendMessage,
    title: ChatText.authGateTitleSendMessage,
    subtitle: ChatText.authGateSubtitleSendMessage,
    prompt: ChatText.authGatePromptSendMessage,
    requiredOperations: <String>[AppCloudOperationIds.chatMessageSendMessage],
  ),
  AuthGateReason.comment: AuthGateEntry(
    reason: AuthGateReason.comment,
    title: UITextConstants.authGateTitleComment,
    subtitle: UITextConstants.authGateSubtitleComment,
    prompt: UITextConstants.authGatePromptComment,
    requiredOperations: <String>[],
  ),
  // 点赞已下放为「游客设备态可写」：LikePost 鉴权为 optional + anonymous_policy=allow，
  // 游客按 deviceActorId 维度真实写入、登录用户按账号维度写入，互不并账。
  // 因此点赞不再触发登录门，requiredOperations 留空；reason 仅表达设备态动作的
  // UX 分类，不映射到 required operation。
  AuthGateReason.like: AuthGateEntry(
    reason: AuthGateReason.like,
    title: UITextConstants.authGateTitleLike,
    subtitle: UITextConstants.authGateSubtitleLike,
    prompt: UITextConstants.authGatePromptLike,
    requiredOperations: <String>[],
  ),
  // 「想去」需要读取账号私有的状态投影；行为写入仍复用 public ReportBehaviors
  // 的 persona/device actor 语义，因此用状态查询这一 required operation 作为 gate
  // 契约锚点，不能复用关注关系的 FollowUser operation。
  AuthGateReason.wishlist: AuthGateEntry(
    reason: AuthGateReason.wishlist,
    title: UITextConstants.authGateTitleWishlist,
    subtitle: UITextConstants.authGateSubtitleWishlist,
    prompt: UITextConstants.authGatePromptWishlist,
    requiredOperations: <String>[
      AppCloudOperationIds.contentPostGetEntityWishlistState,
    ],
  ),
  AuthGateReason.follow: AuthGateEntry(
    reason: AuthGateReason.follow,
    title: UITextConstants.authGateTitleFollow,
    subtitle: UITextConstants.authGateSubtitleFollow,
    prompt: UITextConstants.authGatePromptFollow,
    requiredOperations: <String>[
      AppCloudOperationIds.userPersonaRelationshipFollowUser,
    ],
  ),
  AuthGateReason.greet: AuthGateEntry(
    reason: AuthGateReason.greet,
    title: ChatText.authGateTitleGreet,
    subtitle: ChatText.authGateSubtitleGreet,
    prompt: ChatText.authGatePromptGreet,
    requiredOperations: <String>[],
  ),
  // 关注频道展示「关注的人」的内容流，游客无关注关系，需登录后查看。
  // 关注流走 GetFeed（鉴权快照为 optional），故此处不声明 requiredOperations，
  // 登录约束是产品决策而非 API 强制。
  AuthGateReason.followingFeed: AuthGateEntry(
    reason: AuthGateReason.followingFeed,
    title: UITextConstants.authGateTitleFollowingFeed,
    subtitle: UITextConstants.authGateSubtitleFollowingFeed,
    prompt: UITextConstants.authGatePromptFollowingFeed,
    requiredOperations: <String>[],
  ),
  // 系统分享、复制链接和转发本身不要求账号；只有圈内投放等实际业务写命令
  // 在其独立入口通过对应 operation 的登录门处理。
  AuthGateReason.share: AuthGateEntry(
    reason: AuthGateReason.share,
    title: UITextConstants.authGateTitleShare,
    subtitle: UITextConstants.authGateSubtitleShare,
    prompt: UITextConstants.authGatePromptShare,
    requiredOperations: <String>[],
  ),
  AuthGateReason.personaManage: AuthGateEntry(
    reason: AuthGateReason.personaManage,
    title: UITextConstants.authGateTitlePersona,
    subtitle: UITextConstants.authGateSubtitlePersona,
    prompt: UITextConstants.authGatePromptPersona,
    requiredOperations: <String>[],
  ),
  AuthGateReason.settingsAccount: AuthGateEntry(
    reason: AuthGateReason.settingsAccount,
    title: UITextConstants.authGateTitleSettingsAccount,
    subtitle: UITextConstants.authGateSubtitleSettingsAccount,
    prompt: UITextConstants.authGatePromptSettingsAccount,
    requiredOperations: <String>[],
  ),
  AuthGateReason.mediaUpload: AuthGateEntry(
    reason: AuthGateReason.mediaUpload,
    title: UITextConstants.authGateTitleMediaUpload,
    subtitle: UITextConstants.authGateSubtitleMediaUpload,
    prompt: UITextConstants.authGatePromptMediaUpload,
    requiredOperations: <String>[
      AppCloudOperationIds.contentMediaUploadSessionInitMediaUpload,
    ],
  ),
  AuthGateReason.deletePost: AuthGateEntry(
    reason: AuthGateReason.deletePost,
    title: UITextConstants.authGateTitleDeletePost,
    subtitle: UITextConstants.authGateSubtitleDeletePost,
    prompt: UITextConstants.authGatePromptDeletePost,
    requiredOperations: <String>[],
  ),
  AuthGateReason.report: AuthGateEntry(
    reason: AuthGateReason.report,
    title: UITextConstants.authGateTitleReport,
    subtitle: UITextConstants.authGateSubtitleReport,
    prompt: UITextConstants.authGatePromptReport,
    requiredOperations: <String>[
      AppCloudOperationIds.contentReportCreateReport,
    ],
  ),
  AuthGateReason.blockUser: AuthGateEntry(
    reason: AuthGateReason.blockUser,
    title: UITextConstants.authGateTitleBlockUser,
    subtitle: UITextConstants.authGateSubtitleBlockUser,
    prompt: UITextConstants.authGatePromptBlockUser,
    requiredOperations: <String>[
      AppCloudOperationIds.userPersonaRelationshipBlockUser,
    ],
  ),
  AuthGateReason.homepageWrite: AuthGateEntry(
    reason: AuthGateReason.homepageWrite,
    title: UITextConstants.authGateTitleHomepageWrite,
    subtitle: UITextConstants.authGateSubtitleHomepageWrite,
    prompt: UITextConstants.authGatePromptHomepageWrite,
    requiredOperations: <String>[
      AppCloudOperationIds.entityHomepageSuggestHomepageCandidate,
      AppCloudOperationIds.entityHomepageUpdateClaimedHomepageBasics,
      AppCloudOperationIds.entityHomepageClaimRequestCreateHomepageClaimRequest,
      AppCloudOperationIds.entityHomepageStatusReportCreateHomepageStatusReport,
    ],
  ),
  AuthGateReason.joinCircle: AuthGateEntry(
    reason: AuthGateReason.joinCircle,
    title: UITextConstants.authGateTitleJoinCircle,
    subtitle: UITextConstants.authGateSubtitleJoinCircle,
    prompt: UITextConstants.authGatePromptJoinCircle,
    requiredOperations: <String>[
      AppCloudOperationIds.circleCircleMembershipJoinCircle,
    ],
  ),
  // 添加联系人 / 发起群聊 / 建圈子 属「先开面板、动作再登录」的产品级动作门，
  // 登录约束是产品决策而非单一 required API，故 requiredOperations 留空。
  AuthGateReason.addContact: AuthGateEntry(
    reason: AuthGateReason.addContact,
    title: UITextConstants.authGateTitleAddContact,
    subtitle: UITextConstants.authGateSubtitleAddContact,
    prompt: UITextConstants.authGatePromptAddContact,
    requiredOperations: <String>[],
  ),
  AuthGateReason.startGroupChat: AuthGateEntry(
    reason: AuthGateReason.startGroupChat,
    title: ChatText.authGateTitleStartGroupChat,
    subtitle: ChatText.authGateSubtitleStartGroupChat,
    prompt: ChatText.authGatePromptStartGroupChat,
    requiredOperations: <String>[],
  ),
  AuthGateReason.createCircle: AuthGateEntry(
    reason: AuthGateReason.createCircle,
    title: UITextConstants.authGateTitleCreateCircle,
    subtitle: UITextConstants.authGateSubtitleCreateCircle,
    prompt: UITextConstants.authGatePromptCreateCircle,
    requiredOperations: <String>[],
  ),
  AuthGateReason.startCall: AuthGateEntry(
    reason: AuthGateReason.startCall,
    title: UITextConstants.authGateTitleStartCall,
    subtitle: UITextConstants.authGateSubtitleStartCall,
    prompt: UITextConstants.authGatePromptStartCall,
    requiredOperations: <String>[
      AppCloudOperationIds.rtcCallSessionInitiateCall,
    ],
  ),
  AuthGateReason.generic: AuthGateEntry(
    reason: AuthGateReason.generic,
    title: UITextConstants.authGateTitleGeneric,
    subtitle: UITextConstants.authGateSubtitleGeneric,
    prompt: UITextConstants.authGatePromptGeneric,
    requiredOperations: <String>[],
  ),
};

extension AuthGateReasonX on AuthGateReason {
  AuthGateEntry get entry =>
      authGateMatrix[this] ?? authGateMatrix[AuthGateReason.generic]!;
  String get title => entry.title;
  String get subtitle => entry.subtitle;
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
  // createEntry 是「添加入口动作面板」，游客必须能先看到面板；真正的发布/
  // 图片/视频编辑页仍在 /create 下由路由守卫保护，登录成功按 redirect 回目标态。
  if (loc == AppRoutePaths.createPathTemplate ||
      loc.startsWith('${AppRoutePaths.createPathTemplate}/')) {
    return AuthGateReason.createPost;
  }
  if (loc == AppRoutePaths.blockedUsers) {
    return AuthGateReason.blockUser;
  }
  if (loc == AppRoutePaths.blockedKeywords) {
    return AuthGateReason.settingsAccount;
  }
  if (loc == AppRoutePaths.assistantManagement) {
    return AuthGateReason.settingsAccount;
  }
  if (loc == AppRoutePaths.myReports) {
    return AuthGateReason.report;
  }
  if (loc == AppRoutePaths.chat || loc.startsWith('/chat/')) {
    return AuthGateReason.openChat;
  }
  // 添加联系人是「先开面板、动作再登录」的强入口：主页及其全部子页（扫一扫/
  // 通讯录/搜索/确认）与「我的二维码」都是账号态，直达必须先登录，关闭兜底回首页。
  if (loc == AppRoutePaths.addContact ||
      loc.startsWith('${AppRoutePaths.addContact}/') ||
      loc == AppRoutePaths.myQrCode) {
    return AuthGateReason.addContact;
  }
  return null;
}

enum LoginDismissPolicy { popPrevious, safeFallback, hostControlledClose }

String buildLoginRouteLocation({
  required String reasonName,
  String? redirect,
  String? dismissFallback,
  LoginDismissPolicy dismissPolicy = LoginDismissPolicy.popPrevious,
}) {
  final reason = _trimmedOrNull(reasonName);
  final redirectLocation = _trimmedOrNull(redirect);
  final fallbackLocation = _trimmedOrNull(dismissFallback);
  final query = <String, String>{
    'reason': ?reason,
    'redirect': ?redirectLocation,
    loginDismissFallbackQueryParam: ?fallbackLocation,
    loginGuestDismissPopQueryParam: dismissPolicy.name,
  };
  return Uri(
    path: AppRoutePaths.loginPathTemplate,
    queryParameters: query,
  ).toString();
}

LoginDismissPolicy loginDismissPolicyFromQuery(String? raw) {
  return LoginDismissPolicy.values.firstWhere(
    (value) => value.name == raw,
    orElse: () => LoginDismissPolicy.popPrevious,
  );
}

String currentLoginDismissFallback(BuildContext context) {
  try {
    final location = GoRouterState.of(context).uri.toString().trim();
    return location.isEmpty ? AppRoutePaths.home : location;
  } catch (_) {
    return AppRoutePaths.home;
  }
}

String safeLoginDismissFallback({String? redirect, String? dismissFallback}) {
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
  LoginDismissPolicy dismissPolicy = LoginDismissPolicy.popPrevious,
  bool replace = false,
}) {
  final location = buildLoginRouteLocation(
    reasonName: reasonName,
    redirect: redirect,
    dismissFallback: dismissFallback,
    dismissPolicy: dismissPolicy,
  );
  if (replace) {
    context.go(location);
  } else {
    context.push(location);
  }
}

bool _isLoginSurfaceActive(BuildContext context) {
  try {
    return GoRouter.of(context).routerDelegate.currentConfiguration.uri.path ==
        AppRoutePaths.loginPathTemplate;
  } catch (_) {
    return false;
  }
}

/// 解析登录页标题：优先用 AuthGateReason，其次回退到 [AuthPromptReason]。
String? authGateTitleForReasonName(String? name) {
  final gateReason = authGateReasonForName(name);
  if (gateReason != null) {
    return gateReason.title;
  }
  final promptReason = authPromptReasonForName(name);
  if (promptReason != null) {
    return loginReasonCopyForPromptReason(promptReason).title;
  }
  return null;
}

LoginReasonCopy loginReasonCopyForName(String? name) {
  final gateReason = authGateReasonForName(name);
  if (gateReason != null) {
    return LoginReasonCopy(
      title: gateReason.title,
      subtitle: gateReason.subtitle,
      source: LoginReasonCopySource.localApp,
    );
  }
  final promptReason = authPromptReasonForName(name);
  if (promptReason != null) {
    return loginReasonCopyForPromptReason(promptReason);
  }
  return const LoginReasonCopy(
    title: UITextConstants.loginDefaultTitle,
    subtitle: UITextConstants.loginDefaultSubtitle,
    source: LoginReasonCopySource.localApp,
  );
}

LoginReasonCopy loginReasonCopyForPromptReason(AuthPromptReason reason) {
  return switch (reason) {
    AuthPromptReason.firstRun => const LoginReasonCopy(
      title: UITextConstants.loginTitleFirstRun,
      subtitle: UITextConstants.loginSubtitleFirstRun,
      source: LoginReasonCopySource.localApp,
    ),
    AuthPromptReason.manualLoggedOut => const LoginReasonCopy(
      title: UITextConstants.loginTitleManualLoggedOut,
      subtitle: UITextConstants.loginSubtitleManualLoggedOut,
      source: LoginReasonCopySource.localSession,
    ),
    AuthPromptReason.sessionExpired => const LoginReasonCopy(
      title: UITextConstants.loginTitleReturn,
      subtitle: UITextConstants.loginSubtitleSessionExpired,
      source: LoginReasonCopySource.localSession,
    ),
    AuthPromptReason.accountSuspended => const LoginReasonCopy(
      title: UITextConstants.loginTitleActionRequired,
      subtitle: UITextConstants.loginAccountSuspended,
      source: LoginReasonCopySource.localSession,
    ),
    AuthPromptReason.actionRequired => const LoginReasonCopy(
      title: UITextConstants.loginTitleActionRequired,
      subtitle: UITextConstants.loginSubtitleActionRequired,
      source: LoginReasonCopySource.localApp,
    ),
  };
}

AuthGateReason? authGateReasonForName(String? name) {
  if (name == null || name.isEmpty) {
    return null;
  }
  for (final reason in AuthGateReason.values) {
    if (reason.name == name) {
      return reason;
    }
  }
  return null;
}

AuthPromptReason? authPromptReasonForName(String? name) {
  if (name == null || name.isEmpty) {
    return null;
  }
  for (final reason in AuthPromptReason.values) {
    if (reason.name == name) {
      return reason;
    }
  }
  return null;
}

UiErrorSemantic authGateSemantic(
  BuildContext context, {
  required AuthGateReason reason,
  AuthContinuation? continuation,
  UiErrorScope scope = UiErrorScope.global,
}) {
  return UiErrorSemanticResolver.authRequired(
    context,
    reason: reason,
    continuation: continuation,
    scope: scope,
  );
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
  static DateTime? _lastTriggeredAt;

  @visibleForTesting
  static void resetDebounce() => _lastTriggeredAt = null;

  static bool _isDebounced(AuthGateReason _) {
    final now = DateTime.now();
    final last = _lastTriggeredAt;
    if (last != null && now.difference(last) < _debounceWindow) {
      return true;
    }
    _lastTriggeredAt = now;
    return false;
  }

  static bool isAuthenticated(WidgetRef ref) =>
      ref.read(authSessionControllerProvider).isAuthenticated;
}

/// 无需账号的动作：点赞与系统分享。系统分享仅交给平台，不会伪造外部平台回执；
/// 需要真实业务写入的圈内投放会在它自己的命令入口再次执行鉴权。
///
/// 收口为单一真相源：所有 like/share 入口都通过 [requireLogin] / [runWhenLoggedIn]
/// 统一放行，无需逐个改调用点，避免遗漏导致游客被错误拦截。
const Set<AuthGateReason> guestWritableAuthGateReasons = <AuthGateReason>{
  AuthGateReason.like,
  AuthGateReason.share,
};

/// 拦截受限动作。返回 `true` 表示可继续（已登录或属游客设备态可写动作），
/// `false` 表示已引导登录、调用方应停止。
Future<bool> requireLogin(
  WidgetRef ref,
  BuildContext context,
  AuthGateReason reason, {
  String? redirect,
  String? dismissFallback,
  LoginDismissPolicy dismissPolicy = LoginDismissPolicy.popPrevious,
}) async {
  // 无需账号的点赞/系统分享动作直接放行；它们不创建或伪造站外分享业务事实。
  if (guestWritableAuthGateReasons.contains(reason)) {
    return true;
  }
  if (AuthGate.isAuthenticated(ref)) {
    return true;
  }
  if (_isLoginSurfaceActive(context)) {
    return false;
  }
  if (AuthGate._isDebounced(reason)) {
    return false;
  }
  if (!context.mounted) {
    return false;
  }
  openLoginPage(
    context,
    reasonName: reason.name,
    redirect: redirect,
    dismissFallback: dismissFallback ?? currentLoginDismissFallback(context),
    dismissPolicy: dismissPolicy,
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
  LoginDismissPolicy dismissPolicy = LoginDismissPolicy.popPrevious,
}) {
  unawaited(() async {
    final allowed = await requireLogin(
      ref,
      context,
      reason,
      redirect: redirect,
      dismissFallback: dismissFallback,
      dismissPolicy: dismissPolicy,
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
