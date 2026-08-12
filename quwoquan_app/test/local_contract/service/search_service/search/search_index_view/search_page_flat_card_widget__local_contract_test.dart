import '../../../../../support/service/circle_service/circle_management/circle/circle_query_typed_double.dart';
import '../../../../../support/service/search_service/search/search_feedback_fact/search_feedback_typed_double.dart';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart';
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/search_repository.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/public/search_launch_contract.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_network_results_page.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';

void main() {
  testWidgets(
    'SearchPage renders flat card and navigates its canonical action',
    (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      final router = GoRouter(
        initialLocation: '/',
        routes: <RouteBase>[
          GoRoute(
            path: '/',
            builder: (context, state) => const SearchNetworkResultsPage(
              launchContext: SearchLaunchContext(
                entrySurfaceId: '/search',
                prefilledQuery: '山间',
                initialNetworkTabId: 'all',
              ),
            ),
          ),
          GoRoute(
            path: '/posts/:id',
            builder: (context, state) =>
                Text('destination:${state.pathParameters['id']}'),
          ),
        ],
      );
      addTearDown(router.dispose);

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            circlesListQueryProvider.overrideWithValue(
              InMemoryCircleQueryReader(),
            ),
            searchRepositoryProvider.overrideWithValue(
              const _FlatSearchPageRepository(),
            ),
            searchFeedbackFactAppenderProvider.overrideWithValue(
              SearchFeedbackTypedDouble(),
            ),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await _pumpUntil(
        tester,
        condition: () => find.text('山间路线').evaluate().isNotEmpty,
      );

      expect(find.text('山间路线'), findsOneWidget);
      expect(find.text('两日徒步'), findsOneWidget);
      expect(find.text('没有找到“山间”的结果'), findsNothing);

      await tester.tap(
        find.byKey(
          const ValueKey<String>(
            'search_page_result_action_ref:content-post:opaque-1',
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('destination:opaque-1'), findsOneWidget);
    },
  );
}

final class _FlatSearchPageRepository implements SearchRepository {
  const _FlatSearchPageRepository();

  @override
  Future<SearchResponse> search(
    SearchRequest request, {
    CloudOperationCancellationSignal? cancellation,
    DateTime? deadlineAt,
  }) async {
    return SearchResponse(
      request: request.normalized(),
      sections: const <SearchSection>[],
      pageItems: const <SearchPageResultItem>[
        SearchPageResultItem(
          objectRef: 'ref:content-post:opaque-1',
          resultType: SearchPageObjectType.contentPost,
          title: '山间路线',
          subtitle: '两日徒步',
          snippet: '从营地出发',
          action: '/posts/opaque-1',
        ),
      ],
    );
  }
}

Future<void> _pumpUntil(
  WidgetTester tester, {
  required bool Function() condition,
}) async {
  for (var index = 0; index < 30 && !condition(); index += 1) {
    await tester.pump(const Duration(milliseconds: 100));
  }
  expect(condition(), isTrue);
}
