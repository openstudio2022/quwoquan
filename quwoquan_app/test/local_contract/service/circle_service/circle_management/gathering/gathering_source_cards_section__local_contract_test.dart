// 「近期行动」L0 区块契约：只展示 published 公开行动卡（≤3 条）、
// 为空/读取失败整块不渲染不占位（独立降级，失败进观测通道）、
// 行动卡点击进入公开详情。
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001.t3
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show exceptionTelemetryPortProvider;
import 'package:quwoquan_app/runtime/observability/app_observability_ports.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_source_cards_section.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart'
    show RuntimeFailureBase;

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/runtime/homepage_source_cards_boundary_overrides.dart';

const String _homepageId = 'homepage_sight_west_lake';

final class _QueryReaderDouble implements GatheringQueryReader {
  _QueryReaderDouble({
    this.cards = const <GatheringSourceCardSummary>[],
    this.fail = false,
  });

  final List<GatheringSourceCardSummary> cards;
  final bool fail;
  GatheringBySourceListQuery? lastQuery;

  @override
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  ) async => null;

  @override
  Future<List<GatheringSourceCardSummary>> listBySource(
    GatheringBySourceListQuery query,
  ) async {
    lastQuery = query;
    if (fail) {
      throw StateError('source cards unavailable');
    }
    return cards;
  }

  @override
  Future<GatheringHostCardPage> listByHost(
    GatheringByHostListQuery query,
  ) async => GatheringHostCardPage.empty;

  @override
  Future<GatheringHostCardPage> listMine(GatheringMineListQuery query) async =>
      GatheringHostCardPage.empty;
}

final class _RecordingTelemetry implements ExceptionTelemetryPort {
  final List<String> handledSources = <String>[];

  @override
  Future<void> recordGlobalException({
    required String source,
    required String exceptionText,
    required String stackText,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
    RuntimeFailureBase? runtimeFailure,
    String exceptionType = '',
  }) async {}

  @override
  Future<void> recordHandledException({
    required String source,
    required Object error,
    required StackTrace stackTrace,
    String pageId = 'global.app.runtime',
    String pageName = '',
    String surfaceId = 'global.app.runtime',
    String routeId = 'global.app.runtime',
    String operationId = 'app.runtime.capture_exception',
  }) async {
    handledSources.add(source);
  }

  @override
  Future<void> flushPending() async {}
}

GatheringSourceCardSummary _card(
  String id, {
  String lifecycle = 'published',
  bool full = false,
  int remaining = 3,
  String? dateLabel,
}) => GatheringSourceCardSummary(
  gatheringId: id,
  title: '黄龙晨雾摄影散步 $id',
  dateLabel: dateLabel,
  startAt: DateTime.utc(2026, 8, 15, 9),
  remainingSeats: remaining,
  full: full,
  lifecycleStatusWire: lifecycle,
);

Future<List<String>> _pump(
  WidgetTester tester, {
  required _QueryReaderDouble reader,
  _RecordingTelemetry? telemetry,
}) async {
  final navigations = <String>[];
  final router = GoRouter(
    initialLocation: '/',
    routes: <RouteBase>[
      GoRoute(
        path: '/',
        builder: (_, _) => Scaffold(
          body: GatheringSourceCardsSection(
            sourceObjectTypeRef: 'homepage',
            sourceObjectId: _homepageId,
            isDark: false,
          ),
        ),
      ),
      GoRoute(
        path: AppRoutePaths.gatheringDetailPathTemplate.replaceAll(
          '{id}',
          ':id',
        ),
        builder: (_, state) {
          navigations.add(state.pathParameters['id'] ?? '');
          return const SizedBox();
        },
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        ...sealedCloudBoundaryOverrides(),
        ...homepageSourceCardsBoundaryOverrides(gatheringQueryReader: reader),
        exceptionTelemetryPortProvider.overrideWithValue(
          telemetry ?? _RecordingTelemetry(),
        ),
      ],
      child: MaterialApp.router(routerConfig: router),
    ),
  );
  await tester.pumpAndSettle();
  return navigations;
}

void main() {
  testWidgets('展示至多三条 published 行动卡并可进入公开详情', (tester) async {
    final reader = _QueryReaderDouble(
      cards: <GatheringSourceCardSummary>[
        _card('g1', dateLabel: '本周六上午'),
        _card('g2', full: true, remaining: 0),
        _card('g3', lifecycle: 'draft'),
        _card('g4'),
      ],
    );
    final navigations = await _pump(tester, reader: reader);

    expect(
      find.byKey(const ValueKey<String>('gathering-source-cards-section')),
      findsOneWidget,
    );
    expect(reader.lastQuery?.sourceObjectTypeRef, 'homepage');
    expect(reader.lastQuery?.sourceObjectId, _homepageId);
    // draft 不进 L0 区块（诚实：只展示可加入语义明确的发布态）。
    expect(
      find.byKey(const ValueKey<String>('gathering-source-card-g3')),
      findsNothing,
    );
    expect(find.text('本周六上午'), findsOneWidget);
    expect(find.text(GatheringText.sourceGatheringFullLabel), findsOneWidget);
    expect(
      find.text(GatheringText.sourceGatheringSeatsRemaining(3)),
      findsWidgets,
    );

    await tester.tap(
      find.byKey(const ValueKey<String>('gathering-source-card-g1')),
    );
    await tester.pumpAndSettle();
    expect(navigations, <String>['g1']);
  });

  testWidgets('无公开行动时整块不渲染不占位', (tester) async {
    await _pump(tester, reader: _QueryReaderDouble());

    expect(
      find.byKey(const ValueKey<String>('gathering-source-cards-section')),
      findsNothing,
    );
    expect(find.text(GatheringText.sourceRecentGatheringsTitle), findsNothing);
  });

  testWidgets('读取失败静默降级并进观测通道', (tester) async {
    final telemetry = _RecordingTelemetry();
    await _pump(
      tester,
      reader: _QueryReaderDouble(fail: true),
      telemetry: telemetry,
    );

    expect(
      find.byKey(const ValueKey<String>('gathering-source-cards-section')),
      findsNothing,
    );
    expect(
      telemetry.handledSources,
      contains('circle.gathering.source_cards_section'),
    );
  });
}
