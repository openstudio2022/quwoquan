import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_section.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_timeline_item.g.dart';
import 'package:quwoquan_app/cloud/services/entity/entity_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/entity/pages/homepage_introduction_page.dart';

class _IntroRepository implements HomepageIntroductionRepository {
  _IntroRepository(this.introduction, {this.shouldThrow = false});

  final HomepageIntroduction? introduction;
  final bool shouldThrow;

  @override
  Future<HomepageIntroduction?> getHomepageIntroduction(
    String homepageId,
  ) async {
    if (shouldThrow) {
      throw StateError('intro failed');
    }
    return introduction;
  }
}

Widget _host(HomepageIntroduction? introduction, {bool shouldThrow = false}) {
  return ProviderScope(
    overrides: [
      homepageIntroductionRepositoryProvider.overrideWithValue(
        _IntroRepository(introduction, shouldThrow: shouldThrow),
      ),
    ],
    child: const CupertinoApp(
      home: HomepageIntroductionPage(homepageId: 'homepage_sight_west_lake'),
    ),
  );
}

void main() {
  testWidgets('完整介绍页渲染分节与时间线', (tester) async {
    await tester.pumpWidget(
      _host(
        HomepageIntroduction(
          homepageId: 'homepage_sight_west_lake',
          displayName: '西湖景区',
          homepageType: 'sight',
          summary: '西湖景区摘要',
          sections: <HomepageIntroductionSection>[
            HomepageIntroductionSection(
              kind: 'overview',
              title: '概况',
              bodyMarkdown: '西湖景区位于杭州。',
            ),
            HomepageIntroductionSection(
              kind: 'timeline',
              title: '时间线',
              timelineItems: <HomepageIntroductionTimelineItem>[
                HomepageIntroductionTimelineItem(
                  dateLabel: '今天',
                  text: '围绕西湖的内容和讨论持续沉淀。',
                ),
              ],
            ),
          ],
          sourceRefs: const <String>['fixture:west_lake'],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('认识西湖景区'), findsOneWidget);
    expect(find.text('西湖景区摘要'), findsOneWidget);
    expect(find.text('概况'), findsOneWidget);
    expect(find.textContaining('位于杭州'), findsOneWidget);
    expect(find.text('时间线'), findsOneWidget);
    expect(find.text('今天'), findsOneWidget);
    expect(find.textContaining('持续沉淀'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.textContaining('fixture:west_lake'),
      AppSpacing.twoHundredTwenty,
      scrollable: find.byType(Scrollable).first,
    );
    expect(find.textContaining('fixture:west_lake'), findsOneWidget);
  });

  testWidgets('介绍为空时展示空态', (tester) async {
    await tester.pumpWidget(
      _host(
        HomepageIntroduction(
          homepageId: 'homepage_empty',
          displayName: '空主页',
          homepageType: 'place',
          summary: '',
          sections: const <HomepageIntroductionSection>[],
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('介绍正在整理'), findsOneWidget);
  });

  testWidgets('介绍加载失败时展示可重试错误态', (tester) async {
    await tester.pumpWidget(_host(null, shouldThrow: true));
    await tester.pumpAndSettle();

    expect(find.byType(AppSectionErrorCard), findsOneWidget);
  });
}
