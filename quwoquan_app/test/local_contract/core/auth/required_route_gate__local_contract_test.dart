import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';

/// 直达路由守卫真相源回归测试。
///
/// 关键回环修复：「我的」tab（/profile 本体）必须对游客可浏览，绝不整页拦截，
/// 否则登录页关闭 / 稍后登录会原路返回到 /profile，被守卫立刻再次弹出登录页，
/// 形成「关闭→又弹登录」的死循环。
void main() {
  group('requiredRouteGateForLocation', () {
    test('/profile 本体游客可浏览（不拦截），杜绝关闭后死循环', () {
      expect(requiredRouteGateForLocation(AppRoutePaths.profile), isNull);
    });

    test('首页 / 圈子 / 搜索等浏览页不拦截', () {
      expect(requiredRouteGateForLocation(AppRoutePaths.home), isNull);
      expect(requiredRouteGateForLocation(AppRoutePaths.circles), isNull);
      expect(requiredRouteGateForLocation(AppRoutePaths.globalSearch), isNull);
      expect(requiredRouteGateForLocation('/following'), isNull);
    });

    test('「我的」私密子页需要登录', () {
      expect(
        requiredRouteGateForLocation(AppRoutePaths.profilePersonas),
        AuthGateReason.personaManage,
      );
      expect(
        requiredRouteGateForLocation(AppRoutePaths.profileEdit),
        AuthGateReason.personaManage,
      );
      expect(
        requiredRouteGateForLocation(AppRoutePaths.profileStatsPathTemplate),
        AuthGateReason.personaManage,
      );
    });

    test('添加面板入口不拦截，具体创作页需要登录', () {
      expect(requiredRouteGateForLocation(AppRoutePaths.createEntry), isNull);
      expect(
        requiredRouteGateForLocation(AppRoutePaths.createPathTemplate),
        AuthGateReason.createPost,
      );
    });

    test('消息 tab 与会话详情需要登录', () {
      expect(
        requiredRouteGateForLocation(AppRoutePaths.chat),
        AuthGateReason.openChat,
      );
      expect(
        requiredRouteGateForLocation(AppRoutePaths.chatDetail(id: 'c1')),
        AuthGateReason.openChat,
      );
    });

    test('私助管理页需要登录且关闭登录页回到安全页', () {
      expect(
        requiredRouteGateForLocation(AppRoutePaths.assistantManagement),
        AuthGateReason.settingsAccount,
      );
      expect(
        safeLoginDismissFallback(redirect: AppRoutePaths.assistantManagement),
        AppRoutePaths.home,
      );
    });

    test('防死循环：buildLoginRouteLocation 显式编码安全关闭策略', () {
      final loc = buildLoginRouteLocation(
        reasonName: AuthGateReason.openChat.name,
        redirect: AppRoutePaths.chat,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      );
      final uri = Uri.parse(loc);
      expect(uri.path, AppRoutePaths.loginPathTemplate);
      expect(
        uri.queryParameters[loginGuestDismissPopQueryParam],
        LoginDismissPolicy.safeFallback.name,
      );
      expect(
        loginDismissPolicyFromQuery(
          uri.queryParameters[loginGuestDismissPopQueryParam],
        ),
        LoginDismissPolicy.safeFallback,
      );
      // 即便游客 pop 失败兜底，也只会落到安全页而非受限路由。
      expect(
        safeLoginDismissFallback(
          redirect: AppRoutePaths.chat,
          dismissFallback: AppRoutePaths.home,
        ),
        AppRoutePaths.home,
      );
    });

    test('账号受限登录可保留成功续接，但关闭必回安全首页', () {
      final loc = buildLoginRouteLocation(
        reasonName: AuthPromptReason.accountSuspended.name,
        redirect: AppRoutePaths.chat,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      );
      final uri = Uri.parse(loc);
      expect(
        uri.queryParameters['reason'],
        AuthPromptReason.accountSuspended.name,
      );
      expect(uri.queryParameters['redirect'], AppRoutePaths.chat);
      expect(
        loginDismissPolicyFromQuery(
          uri.queryParameters[loginGuestDismissPopQueryParam],
        ),
        LoginDismissPolicy.safeFallback,
      );
      expect(
        safeLoginDismissFallback(
          redirect: AppRoutePaths.chat,
          dismissFallback: AppRoutePaths.home,
        ),
        AppRoutePaths.home,
      );
      final copy = loginReasonCopyForPromptReason(
        AuthPromptReason.accountSuspended,
      );
      expect(copy.subtitle, contains('限制'));
    });

    test('行内动作门默认允许 guest pop（登录关闭原路返回可浏览页）', () {
      final loc = buildLoginRouteLocation(
        reasonName: AuthGateReason.comment.name,
      );
      final uri = Uri.parse(loc);
      expect(
        uri.queryParameters[loginGuestDismissPopQueryParam],
        LoginDismissPolicy.popPrevious.name,
      );
      expect(
        loginDismissPolicyFromQuery(
          uri.queryParameters[loginGuestDismissPopQueryParam],
        ),
        LoginDismissPolicy.popPrevious,
      );
    });

    test('safeLoginDismissFallback 会把受限路由和首页关注态降级到安全页', () {
      expect(
        safeLoginDismissFallback(redirect: AppRoutePaths.chat),
        AppRoutePaths.home,
      );
      expect(
        safeLoginDismissFallback(redirect: AppRoutePaths.createPathTemplate),
        AppRoutePaths.home,
      );
      expect(
        safeLoginDismissFallback(redirect: '/following'),
        AppRoutePaths.home,
      );
      expect(
        safeLoginDismissFallback(redirect: AppRoutePaths.profilePersonas),
        AppRoutePaths.profile,
      );
      expect(
        safeLoginDismissFallback(dismissFallback: AppRoutePaths.settings),
        AppRoutePaths.settings,
      );
    });
  });
}
