import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/models/creator_impact_summary.dart';
import 'package:quwoquan_app/ui/user/widgets/creator_impact_card.dart';

Widget _host(CreatorImpactSummary summary) {
  return MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: CreatorImpactCard(summary: summary, isDark: false),
      ),
    ),
  );
}

void main() {
  group('CreatorImpactCard', () {
    testWidgets('空摘要展示鼓励发布空态，无事实行', (tester) async {
      await tester.pumpWidget(
        _host(const CreatorImpactSummary(facts: <CreatorImpactFact>[])),
      );

      expect(find.text(UITextConstants.creatorImpactTitle), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('creator-impact-empty')),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey<String>('creator-impact-fact-relationship'),
        ),
        findsNothing,
      );
    });

    testWidgets('非空摘要逐条渲染真实计数与叙事', (tester) async {
      const summary = CreatorImpactSummary(
        facts: <CreatorImpactFact>[
          CreatorImpactFact(
            category: CreatorImpactCategory.appreciation,
            count: 480,
            label: '收获的赞同',
            narrative: '你的内容累计获得 480 次赞同',
          ),
          CreatorImpactFact(
            category: CreatorImpactCategory.relationship,
            count: 12,
            label: '关注你的人',
            narrative: '12 人因为你的内容关注了你',
          ),
        ],
      );

      await tester.pumpWidget(_host(summary));

      expect(
        find.byKey(const ValueKey<String>('creator-impact-empty')),
        findsNothing,
      );
      expect(
        find.byKey(
          const ValueKey<String>('creator-impact-fact-appreciation'),
        ),
        findsOneWidget,
      );
      expect(
        find.byKey(
          const ValueKey<String>('creator-impact-fact-relationship'),
        ),
        findsOneWidget,
      );
      expect(find.text('480'), findsOneWidget);
      expect(find.text('你的内容累计获得 480 次赞同'), findsOneWidget);
    });
  });
}
