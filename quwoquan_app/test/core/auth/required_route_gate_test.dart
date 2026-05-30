import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/auth/auth_gate.dart';

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
        requiredRouteGateForLocation(AppRoutePaths.profileComments),
        AuthGateReason.personaManage,
      );
      expect(
        requiredRouteGateForLocation(AppRoutePaths.profileStatsPathTemplate),
        AuthGateReason.personaManage,
      );
    });

    test('创作入口需要登录', () {
      expect(
        requiredRouteGateForLocation(AppRoutePaths.createEntry),
        AuthGateReason.createPost,
      );
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
  });
}
