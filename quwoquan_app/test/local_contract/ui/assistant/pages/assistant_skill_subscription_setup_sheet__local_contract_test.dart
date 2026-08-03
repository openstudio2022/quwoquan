// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_subscription_setup_sheet.dart';

void main() {
  testWidgets('creates a timezone-bound daily rule without exposing cron', (
    tester,
  ) async {
    AssistantSkillSubscriptionSetup? result;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            onPressed: () async {
              result = await showAssistantSkillSubscriptionSetupSheet(
                context: context,
                skillName: '贴身旅行管家',
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(
      find.byKey(
        const ValueKey<String>('assistant_skill_subscription_setup_sheet'),
      ),
      findsOneWidget,
    );
    expect(find.textContaining('* * *'), findsNothing);
    await tester.enterText(
      find.byKey(
        const ValueKey<String>('assistant_skill_subscription_setup_topic'),
      ),
      '关注西湖行程天气、交通变化和集合时间',
    );
    final save = find.byKey(
      const ValueKey<String>('assistant_skill_subscription_setup_save'),
    );
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();

    expect(result?.rawText, '关注西湖行程天气、交通变化和集合时间');
    expect(result?.cron, '0 8 * * *');
    expect(result?.timezone, 'Asia/Shanghai');
  });

  testWidgets('rejects an empty reminder topic', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) => CupertinoButton(
            onPressed: () => showAssistantSkillSubscriptionSetupSheet(
              context: context,
              skillName: '贴身旅行管家',
            ),
            child: const Text('open'),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(
        const ValueKey<String>('assistant_skill_subscription_setup_topic'),
      ),
      '   ',
    );
    final save = find.byKey(
      const ValueKey<String>('assistant_skill_subscription_setup_save'),
    );
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();

    expect(
      find.byKey(
        const ValueKey<String>('assistant_skill_subscription_setup_error'),
      ),
      findsOneWidget,
    );
  });
}
