import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/discovery/pages/home_page.dart';
import 'package:quwoquan_app/ui/discovery/widgets/unified_object_card.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A3：今日交集对象卡行动按钮 → trackFollow 回流带 dimension + tagRefs。
Widget _buildApp(BehaviorRepository repo) {
  return ProviderScope(
    overrides: [behaviorRepositoryProvider.overrideWithValue(repo)],
    child: ScreenUtilInit(
      designSize: const Size(393, 852),
      child: MaterialApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) =>
                  const Scaffold(body: HomePage(routeLocation: '/')),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (_, _) => const Scaffold(body: SizedBox()),
            ),
            GoRoute(path: '/search', builder: (_, _) => const SizedBox()),
          ],
        ),
      ),
    ),
  );
}

void _suppressExpectedErrors() {
  final original = FlutterError.onError;
  FlutterError.onError = (details) {
    final message = details.exceptionAsString();
    if (message.contains('HTTP request failed') ||
        message.contains('NetworkImageLoadException') ||
        message.contains('overflowed')) {
      return;
    }
    original?.call(details);
  };
}

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues(const <String, Object>{});
  });

  testWidgets('点击「关注」对象卡行动 → trackFollow 带 intersectionDimension + tagRefs', (
    tester,
  ) async {
    _suppressExpectedErrors();
    final repo = MockBehaviorRepository();
    await tester.pumpWidget(_buildApp(repo));
    await tester.pump(const Duration(milliseconds: 300));

    // mock m1 person reason → 行动按钮「关注」（actionType=follow）。
    final followAction = find.descendant(
      of: find.byType(UnifiedObjectCard),
      matching: find.text('关注'),
    );
    expect(followAction, findsOneWidget);

    await tester.tap(followAction);
    await tester.pumpAndSettle();

    // tracker 批量缓冲，显式 flush 后断言。
    final container = ProviderScope.containerOf(
      tester.element(find.byType(MaterialApp)),
    );
    await container.read(contentBehaviorTrackerProvider).flush();

    final follows = repo.recorded
        .where((event) => event.action == BehaviorAction.follow)
        .toList();
    expect(follows, isNotEmpty);
    final follow = follows.first;
    expect(follow.contentId, 'u1');
    expect(follow.intersectionDimension, 'identity');
    expect(follow.intersectionTagRefs, contains('identity/campus/xdf'));
    expect(follow.referralSource, ReferralSource.organicFeed);
  });
}
