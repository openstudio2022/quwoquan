import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/author_impact_summary.g.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/user/widgets/author_impact_card.dart';

Widget _host(AuthorImpactSummary summary, {required bool isMine}) {
  return MaterialApp(
    home: Scaffold(
      body: SingleChildScrollView(
        child: AuthorImpactCard(
          summary: summary,
          isDark: false,
          isMine: isMine,
        ),
      ),
    ),
  );
}

void main() {
  group('AuthorImpactCard', () {
    testWidgets('mine 空摘要展示「我的影响力」鼓励发布空态，无事实行', (tester) async {
      await tester.pumpWidget(
        _host(AuthorImpactSummary(authorId: 'u1'), isMine: true),
      );

      expect(find.text(UITextConstants.profileImpactTitleMine), findsOneWidget);
      expect(find.byKey(AuthorImpactCard.emptyKey), findsOneWidget);
      expect(
        find.byKey(const ValueKey<String>('author-impact-fact-community')),
        findsNothing,
      );
    });

    testWidgets('other 空摘要整卡收起（不造假、不占位）', (tester) async {
      await tester.pumpWidget(
        _host(AuthorImpactSummary(authorId: 'u2'), isMine: false),
      );

      expect(find.byKey(AuthorImpactCard.cardKey), findsNothing);
    });

    testWidgets('other 非空摘要展示「TA的影响」，逐条直出云侧 displayText', (tester) async {
      final summary = AuthorImpactSummary(
        authorId: 'u2',
        total: 35,
        items: <AuthorImpactItem>[
          AuthorImpactItem(
            helpType: 'community',
            action: 'join',
            intersectionDimension: 'interest',
            count: 23,
            displayText: '23人加入相关圈子',
          ),
          AuthorImpactItem(
            helpType: 'decision',
            action: 'share',
            intersectionDimension: 'content',
            count: 12,
            displayText: '12人转发了TA的内容',
          ),
        ],
      );

      await tester.pumpWidget(_host(summary, isMine: false));

      expect(
        find.text(UITextConstants.profileImpactTitleOther),
        findsOneWidget,
      );
      expect(find.byKey(AuthorImpactCard.emptyKey), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('author-impact-fact-community')),
        findsOneWidget,
      );
      expect(
        find.byKey(const ValueKey<String>('author-impact-fact-decision')),
        findsOneWidget,
      );
      expect(find.text('23人加入相关圈子'), findsOneWidget);
      expect(find.text('12人转发了TA的内容'), findsOneWidget);
    });

    testWidgets('摘要区最多渲染前 3 条（规格：取前 3 条 displayText）', (tester) async {
      final summary = AuthorImpactSummary(
        authorId: 'u3',
        total: 40,
        items: <AuthorImpactItem>[
          for (var i = 0; i < 5; i++)
            AuthorImpactItem(
              helpType: 'kind$i',
              action: 'a',
              intersectionDimension: 'content',
              count: 10 - i,
              displayText: '事实行 $i',
            ),
        ],
      );

      await tester.pumpWidget(_host(summary, isMine: true));

      expect(find.text('事实行 0'), findsOneWidget);
      expect(find.text('事实行 2'), findsOneWidget);
      expect(find.text('事实行 3'), findsNothing);
      expect(find.text('事实行 4'), findsNothing);
    });
  });
}
