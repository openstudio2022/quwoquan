// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#req-008
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/my_gatherings_entry_card.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

final class _StubGatheringQueryReader implements GatheringQueryReader {
  _StubGatheringQueryReader({
    this.page = GatheringHostCardPage.empty,
    this.failure,
  });

  final GatheringHostCardPage page;
  final Object? failure;

  @override
  Future<GatheringHostCardPage> listByHost(
    GatheringByHostListQuery query,
  ) async {
    final error = failure;
    if (error != null) {
      throw error;
    }
    return page;
  }

  @override
  Future<GatheringHostCardPage> listMine(GatheringMineListQuery query) async {
    final error = failure;
    if (error != null) {
      throw error;
    }
    return page;
  }

  @override
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  ) async => null;

  @override
  Future<List<GatheringSourceCardSummary>> listBySource(
    GatheringBySourceListQuery query,
  ) async => const <GatheringSourceCardSummary>[];
}

class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      ownerId: 'test-user',
      activePersonaId: 'test-persona',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

List<Override> _boundaryOverrides(_StubGatheringQueryReader reader) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    gatheringQueryReaderProvider.overrideWithValue(reader),
  ];
}

Future<void> _pumpCard(
  WidgetTester tester,
  _StubGatheringQueryReader reader, {
  List<GoRoute> extraRoutes = const <GoRoute>[],
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: _boundaryOverrides(reader),
      child: CupertinoApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: <GoRoute>[
            GoRoute(
              path: '/',
              builder: (_, _) => const CupertinoPageScaffold(
                child: MyGatheringsEntryCard(isDark: false),
              ),
            ),
            GoRoute(
              path: '/profile/gatherings',
              builder: (_, state) => Text(
                'MY_GATHERINGS:${state.uri.queryParameters['segment'] ?? ''}',
              ),
            ),
            ...extraRoutes,
          ],
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

GatheringHostCardSummary _card(String id, String temporal) {
  return GatheringHostCardSummary(
    gatheringId: id,
    title: 'title-$id',
    dateLabel: null,
    startAt: null,
    remainingSeats: 1,
    full: false,
    lifecycleStatusWire: 'published',
    temporalPhaseWire: temporal,
  );
}

void main() {
  testWidgets('存在即将开始的公开行动时展示计数徽标', (tester) async {
    final reader = _StubGatheringQueryReader(
      page: GatheringHostCardPage(
        items: <GatheringHostCardSummary>[
          _card('g1', 'upcoming'),
          _card('g2', 'in_progress'),
          _card('g3', 'ended'),
        ],
        nextCursor: '',
        hasMore: false,
      ),
    );
    await _pumpCard(tester, reader);
    expect(find.byKey(MyGatheringsEntryCard.cardKey), findsOneWidget);
    expect(
      find.text(GatheringText.myGatheringsUpcomingBadge(2)),
      findsOneWidget,
    );
  });

  testWidgets('无行动折叠为单行入口文案，不渲染空列表', (tester) async {
    final reader = _StubGatheringQueryReader();
    await _pumpCard(tester, reader);
    expect(find.byKey(MyGatheringsEntryCard.cardKey), findsOneWidget);
    expect(find.text(GatheringText.myGatheringsEntryHint), findsOneWidget);
  });

  testWidgets('读面失败降级为纯入口行（不阻塞主页、不伪造计数）', (tester) async {
    final reader = _StubGatheringQueryReader(
      failure: StateError('host list unavailable'),
    );
    await _pumpCard(tester, reader);
    expect(find.byKey(MyGatheringsEntryCard.cardKey), findsOneWidget);
    expect(find.text(GatheringText.myGatheringsEntryHint), findsOneWidget);
  });

  testWidgets('点击入口进入我的行动分组页', (tester) async {
    final reader = _StubGatheringQueryReader();
    await _pumpCard(tester, reader);
    await tester.tap(find.byKey(MyGatheringsEntryCard.cardKey));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.textContaining('MY_GATHERINGS:'), findsOneWidget);
  });
}
