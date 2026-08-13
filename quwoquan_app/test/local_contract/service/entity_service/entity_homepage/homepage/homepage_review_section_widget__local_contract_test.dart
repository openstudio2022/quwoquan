// HomepageReviewSection（口碑子 Tab 评价区）迁移到 homepage 壳后的直接 Widget 契约：
// 空态诚实渲染、真实评价列表来自 HomepageReviewQuery 公开读面、
// 写入口以 requireAuth 闸口分流（游客中止不打开编辑器）。
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show ObjectHomepageText;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show homepageReviewCommandWriterProvider, homepageReviewQueryProvider;
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_review_section.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage_review/homepage_review_facets_typed_double.dart';

const String _homepageId = 'homepage_sight_west_lake';

Widget _host(
  InMemoryHomepageReviewFacet facet, {
  Future<bool> Function()? requireAuth,
}) {
  return ProviderScope(
    overrides: <Override>[
      ...sealedCloudBoundaryOverrides(),
      homepageReviewQueryProvider.overrideWithValue(facet),
      homepageReviewCommandWriterProvider.overrideWithValue(facet),
    ],
    child: CupertinoApp(
      home: CupertinoPageScaffold(
        child: SingleChildScrollView(
          child: HomepageReviewSection(
            homepageId: _homepageId,
            requireAuth: requireAuth,
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('无评价时展示诚实空态与写入口', (tester) async {
    final facet = InMemoryHomepageReviewFacet(
      activePersonaId: 'persona-review-viewer',
    );
    await tester.pumpWidget(_host(facet));
    await tester.pumpAndSettle();

    expect(
      find.text(ObjectHomepageText.homepageReviewEmptyTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('homepage-review-write-entry')),
      findsOneWidget,
    );
    expect(
      find.text(ObjectHomepageText.homepageReviewWriteAction),
      findsOneWidget,
    );
  });

  testWidgets('评价列表来自公开读面并展示作者与正文', (tester) async {
    final facet = InMemoryHomepageReviewFacet(
      activePersonaId: 'persona-review-author',
    );
    await facet.create(
      CreateHomepageReviewCommand(
        homepageId: _homepageId,
        rating: 5,
        body: '湖畔晨雾非常值得早起',
        tagRefs: const <String>['风景'],
        authorDisplayNameSnapshot: '契约旅行者',
        authorAvatarUrlSnapshot: '',
      ),
    );
    await tester.pumpWidget(_host(facet));
    await tester.pumpAndSettle();

    expect(find.text('湖畔晨雾非常值得早起'), findsOneWidget);
    expect(find.text('契约旅行者'), findsOneWidget);
    expect(
      find.text(ObjectHomepageText.homepageReviewEmptyTitle),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('homepage-review-write-entry')),
      findsOneWidget,
    );
  });

  testWidgets('requireAuth 返回 false 时写入口中止且不打开编辑器', (tester) async {
    var gateCalls = 0;
    final facet = InMemoryHomepageReviewFacet(
      activePersonaId: 'persona-review-guest',
    );
    await tester.pumpWidget(
      _host(
        facet,
        requireAuth: () async {
          gateCalls += 1;
          return false;
        },
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const ValueKey<String>('homepage-review-write-entry')),
    );
    await tester.pumpAndSettle();

    expect(gateCalls, 1);
    expect(
      find.byKey(const ValueKey<String>('homepage-review-sheet')),
      findsNothing,
      reason: '游客闸口中止后不得打开评价编辑器',
    );
  });
}
