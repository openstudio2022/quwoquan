/// L1a Entity/HomepageReview：写评价 sheet 交互合同
/// （星级必选、提交载荷形状、编辑预填）。
library;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_review_sheet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageReviewStatus, HomepageReviewView;

Widget _host({
  required void Function(HomepageReviewDraftResult?) onResult,
  HomepageReviewView? initial,
  List<String> tagOptions = const <String>[],
}) {
  return CupertinoApp(
    home: Builder(
      builder: (context) => CupertinoButton(
        key: const ValueKey<String>('open-review-sheet'),
        onPressed: () async {
          final result = await showHomepageReviewSheet(
            context,
            initial: initial,
            tagOptions: tagOptions,
          );
          onResult(result);
        },
        child: const Text('open'),
      ),
    ),
  );
}

void main() {
  testWidgets('未选星级提交给出校验提示且不关闭', (tester) async {
    HomepageReviewDraftResult? result;
    await tester.pumpWidget(_host(onResult: (value) => result = value));
    await tester.tap(find.byKey(const ValueKey<String>('open-review-sheet')));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-submit')),
    );
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.homepageReviewRatingRequired),
      findsOneWidget,
    );
    expect(result, isNull);
  });

  testWidgets('选星 + 正文 + 标签后提交返回载荷', (tester) async {
    HomepageReviewDraftResult? result;
    await tester.pumpWidget(
      _host(
        onResult: (value) => result = value,
        tagOptions: const <String>['publish/tags/scenery'],
      ),
    );
    await tester.tap(find.byKey(const ValueKey<String>('open-review-sheet')));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-star-4')),
    );
    await tester.pump();
    await tester.enterText(
      find.byKey(const ValueKey<String>('homepage-review-body-field')),
      '很棒的体验',
    );
    await tester.tap(find.text('scenery'));
    await tester.pump();
    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-submit')),
    );
    await tester.pumpAndSettle();

    expect(result, isNotNull);
    expect(result!.rating, 4);
    expect(result!.body, '很棒的体验');
    expect(result!.tagRefs, contains('publish/tags/scenery'));
  });

  testWidgets('编辑模式预填我的评价并显示保存文案', (tester) async {
    final mine = HomepageReviewView(
      id: 'r1',
      homepageId: 'hp-1',
      authorPersonaId: 'p1',
      rating: 3,
      status: HomepageReviewStatus.active,
      createdAt: DateTime.utc(2026, 7, 19),
      updatedAt: DateTime.utc(2026, 7, 19),
      body: '原有正文',
      tagRefs: const <String>['publish/tags/scenery'],
    );
    await tester.pumpWidget(_host(onResult: (_) {}, initial: mine));
    await tester.tap(find.byKey(const ValueKey<String>('open-review-sheet')));
    await tester.pumpAndSettle();

    expect(
      find.text(UITextConstants.homepageReviewSheetEditTitle),
      findsOneWidget,
    );
    expect(
      find.text(UITextConstants.homepageReviewUpdateAction),
      findsOneWidget,
    );
    expect(find.text('原有正文'), findsOneWidget);
  });
}
