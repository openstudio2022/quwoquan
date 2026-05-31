import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/discovery/widgets/unified_object_card.dart';

/// A2：统一对象推荐卡（人/地点事物/圈子/组织四类同一卡语言）。
Widget _wrap(Widget child) {
  return CupertinoApp(
    home: CupertinoPageScaffold(
      child: Center(child: child),
    ),
  );
}

IntersectionReason _reason({
  required String relationKind,
  required String actionType,
  String displayText = '你和 TA 的交集',
  int sharedCount = 3,
}) {
  return IntersectionReason(
    relationKind: relationKind,
    actionType: actionType,
    displayText: displayText,
    sharedCount: sharedCount,
    actionTargetId: 'target-1',
  );
}

void main() {
  group('UnifiedObjectCard 四类对象同一卡语言', () {
    test('relationKind → 对象类型解析覆盖四类', () {
      expect(
        UnifiedObjectKind.fromRelationKind('person'),
        UnifiedObjectKind.person,
      );
      expect(
        UnifiedObjectKind.fromRelationKind('place'),
        UnifiedObjectKind.place,
      );
      expect(
        UnifiedObjectKind.fromRelationKind('circle'),
        UnifiedObjectKind.circle,
      );
      expect(UnifiedObjectKind.fromRelationKind('org'), UnifiedObjectKind.org);
    });

    testWidgets('四类对象卡均渲染 displayText 且不抛异常', (tester) async {
      for (final kind in const <String>['person', 'place', 'circle', 'org']) {
        await tester.pumpWidget(
          _wrap(
            UnifiedObjectCard(
              reason: _reason(
                relationKind: kind,
                actionType: 'view',
                displayText: '交集 $kind',
              ),
              isDark: false,
            ),
          ),
        );
        expect(find.text('交集 $kind'), findsOneWidget);
        expect(find.byType(UnifiedObjectCard), findsOneWidget);
      }
    });

    testWidgets('行动按钮文案随 actionType 映射（关注/加入/加好友/查看）', (tester) async {
      Future<void> pumpAction(String actionType) async {
        await tester.pumpWidget(
          _wrap(
            UnifiedObjectCard(
              reason: _reason(relationKind: 'person', actionType: actionType),
              isDark: false,
            ),
          ),
        );
      }

      await pumpAction('follow');
      expect(find.text(UITextConstants.homeObjectActionFollow), findsOneWidget);
      await pumpAction('join');
      expect(find.text(UITextConstants.homeObjectActionJoin), findsOneWidget);
      await pumpAction('add_contact');
      expect(
        find.text(UITextConstants.homeObjectActionAddContact),
        findsOneWidget,
      );
      await pumpAction('view');
      expect(find.text(UITextConstants.homeObjectActionView), findsOneWidget);
    });

    testWidgets('共同点计数展示；count<=0 不展示', (tester) async {
      await tester.pumpWidget(
        _wrap(
          UnifiedObjectCard(
            reason: _reason(
              relationKind: 'person',
              actionType: 'follow',
              sharedCount: 5,
            ),
            isDark: false,
          ),
        ),
      );
      expect(find.text(UITextConstants.homeObjectSharedCount(5)), findsOneWidget);

      await tester.pumpWidget(
        _wrap(
          UnifiedObjectCard(
            reason: _reason(
              relationKind: 'person',
              actionType: 'follow',
              sharedCount: 0,
            ),
            isDark: false,
          ),
        ),
      );
      expect(
        find.textContaining(UITextConstants.homeObjectSharedCountSuffix),
        findsNothing,
      );
    });

    testWidgets('双主题均可渲染（浅色/深色）', (tester) async {
      for (final isDark in const <bool>[false, true]) {
        await tester.pumpWidget(
          _wrap(
            UnifiedObjectCard(
              reason: _reason(relationKind: 'circle', actionType: 'join'),
              isDark: isDark,
            ),
          ),
        );
        expect(tester.takeException(), isNull);
        expect(find.byType(UnifiedObjectCard), findsOneWidget);
      }
    });

    testWidgets('行动按钮热区 ≥ 44 且回调触发', (tester) async {
      var actionCount = 0;
      var openCount = 0;
      await tester.pumpWidget(
        _wrap(
          UnifiedObjectCard(
            reason: _reason(relationKind: 'person', actionType: 'follow'),
            isDark: false,
            onAction: () => actionCount++,
            onOpen: () => openCount++,
          ),
        ),
      );

      final button = find.byType(CupertinoButton);
      expect(button, findsOneWidget);
      expect(
        tester.getSize(button).height,
        greaterThanOrEqualTo(AppSpacing.minInteractiveSize),
      );

      await tester.tap(button);
      await tester.pump();
      expect(actionCount, 1);

      await tester.tap(find.text('你和 TA 的交集'));
      await tester.pump();
      expect(openCount, 1);
    });
  });
}
