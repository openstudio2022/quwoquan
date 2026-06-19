import 'package:flutter/cupertino.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/components/object_page/interactive_intersection_text.dart';
import 'package:quwoquan_app/components/object_page/intersection_target_navigator.dart';

void main() {
  test('IntersectionTargetNavigator 使用 metadata 路由逻辑名解析对象页', () {
    expect(
      IntersectionTargetNavigator.resolvePath(
        IntersectionTarget(
          objectId: 'fixture_user_lin',
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      ),
      '/user/fixture_user_lin',
    );
    expect(
      IntersectionTargetNavigator.resolvePath(
        IntersectionTarget(
          objectId: 'circle_photo',
          objectKind: 'circle',
          routeId: 'circleDetail',
        ),
      ),
      '/circle/circle_photo',
    );
    expect(
      IntersectionTargetNavigator.resolvePath(
        IntersectionTarget(
          objectId: 'homepage_dali',
          objectKind: 'place',
          routeId: 'homepageDetail',
        ),
      ),
      '/homepages/homepage_dali',
    );
    expect(
      IntersectionTargetNavigator.resolvePath(
        IntersectionTarget(
          objectId: 'relationship',
          objectKind: 'tag',
          routeId: 'myIntersections',
        ),
        sourceRef: 'sharedFollowees',
      ),
      '/profile/intersections?dimension=relationship&sourceRef=sharedFollowees',
    );
  });

  testWidgets('InteractiveIntersectionText 优先响应名字/数字 span，再由整行兜底', (
    tester,
  ) async {
    final tapped = <String>[];
    await tester.pumpWidget(
      CupertinoApp(
        home: Center(
          child: InteractiveIntersectionText(
            fallbackText: '你与林清越等 3 位都来这里互动过',
            spans: <IntersectionTextSpan>[
              IntersectionTextSpan(text: '你与', role: 'plain'),
              IntersectionTextSpan(
                text: '林清越',
                role: 'object',
                target: IntersectionTarget(
                  objectId: 'fixture_user_lin',
                  objectKind: 'person',
                  routeId: 'userProfile',
                ),
              ),
              IntersectionTextSpan(text: '等 ', role: 'plain'),
              IntersectionTextSpan(
                text: '3',
                role: 'count',
                target: IntersectionTarget(
                  objectId: 'relationship',
                  objectKind: 'tag',
                  routeId: 'myIntersections',
                ),
              ),
              IntersectionTextSpan(text: ' 位都来这里互动过', role: 'plain'),
            ],
            onSpanTap: (span) => tapped.add(span.role),
            onFallbackTap: () => tapped.add('fallback'),
          ),
        ),
      ),
    );

    final richText = tester.widget<RichText>(
      find.descendant(
        of: find.byType(InteractiveIntersectionText),
        matching: find.byType(RichText),
      ),
    );
    final root = richText.text as TextSpan;
    final tappable = <TextSpan>[];
    void collect(TextSpan span) {
      if (span.recognizer is TapGestureRecognizer) {
        tappable.add(span);
      }
      final children = span.children;
      if (children == null) return;
      for (final child in children) {
        if (child is TextSpan) collect(child);
      }
    }

    collect(root);
    expect(tappable.map((span) => span.text).toList(), <String>['林清越', '3']);
    for (final span in tappable) {
      (span.recognizer! as TapGestureRecognizer).onTap!();
    }

    expect(tapped, <String>['object', 'count']);
  });

  testWidgets('span target 可通过统一 navigator 跳转用户主页', (tester) async {
    final navigator = IntersectionTargetNavigator();
    await tester.pumpWidget(
      CupertinoApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) => Center(
                child: CupertinoButton(
                  child: const Text('open'),
                  onPressed: () {
                    navigator.open(
                      context,
                      IntersectionTarget(
                        objectId: 'fixture_user_lin',
                        objectKind: 'person',
                        routeId: 'userProfile',
                      ),
                    );
                  },
                ),
              ),
            ),
            GoRoute(
              path: '/user/:username',
              builder: (context, state) => Center(
                child: Text('USER:${state.pathParameters['username']}'),
              ),
            ),
          ],
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.text('USER:fixture_user_lin'), findsOneWidget);
  });

  testWidgets('count span target 可通过统一 navigator 跳转我的交集列表', (tester) async {
    final navigator = IntersectionTargetNavigator();
    await tester.pumpWidget(
      CupertinoApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: [
            GoRoute(
              path: '/',
              builder: (context, state) => Center(
                child: CupertinoButton(
                  child: const Text('open-count'),
                  onPressed: () {
                    navigator.open(
                      context,
                      IntersectionTarget(
                        objectId: 'relationship',
                        objectKind: 'tag',
                        routeId: 'myIntersections',
                      ),
                      sourceRef: 'sharedFollowees',
                    );
                  },
                ),
              ),
            ),
            GoRoute(
              path: '/profile/intersections',
              builder: (context, state) => Center(
                child: Text(
                  'INTERSECTIONS:${state.uri.queryParameters['dimension']}:${state.uri.queryParameters['sourceRef']}',
                ),
              ),
            ),
          ],
        ),
      ),
    );

    await tester.tap(find.text('open-count'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(
      find.text('INTERSECTIONS:relationship:sharedFollowees'),
      findsOneWidget,
    );
  });
}
