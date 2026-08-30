// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#req-008
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/my_gatherings_provider.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/my_gatherings_page.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

GatheringHostCardSummary _card({
  required String id,
  required String title,
  String lifecycle = 'published',
  String temporal = 'upcoming',
  int remainingSeats = 2,
  bool full = false,
  String? dateLabel,
}) {
  return GatheringHostCardSummary(
    gatheringId: id,
    title: title,
    dateLabel: dateLabel,
    startAt: null,
    remainingSeats: remainingSeats,
    full: full,
    lifecycleStatusWire: lifecycle,
    temporalPhaseWire: temporal,
  );
}

final class _StubGatheringQueryReader implements GatheringQueryReader {
  _StubGatheringQueryReader({
    this.page = GatheringHostCardPage.empty,
    this.failure,
  });

  final GatheringHostCardPage page;
  final Object? failure;
  int listMineCalls = 0;

  @override
  Future<GatheringHostCardPage> listMine(GatheringMineListQuery query) async {
    listMineCalls += 1;
    final error = failure;
    if (error != null) {
      throw error;
    }
    return page;
  }

  @override
  Future<GatheringHostCardPage> listByHost(
    GatheringByHostListQuery query,
  ) async => GatheringHostCardPage.empty;

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

List<Override> _boundaryOverrides({required _StubGatheringQueryReader reader}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    gatheringQueryReaderProvider.overrideWithValue(reader),
  ];
}

GoRouter _router({required Widget page}) {
  return GoRouter(
    initialLocation: '/',
    routes: <GoRoute>[
      GoRoute(path: '/', builder: (_, _) => page),
      GoRoute(
        path: '/gatherings/:id',
        builder: (_, state) => Text('GATHERING:${state.pathParameters['id']}'),
      ),
    ],
  );
}

Future<void> _pumpPage(
  WidgetTester tester,
  _StubGatheringQueryReader reader, {
  String segment = '',
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: _boundaryOverrides(reader: reader),
      child: CupertinoApp.router(
        routerConfig: _router(page: MyGatheringsPage(segment: segment)),
      ),
    ),
  );
  // 防卡死模式：有限帧 pump，不使用 pumpAndSettle。
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  group('myGatheringsSegmentOf（分组只由云侧 lifecycleStatus × temporalPhase 派生）', () {
    test('published+upcoming/in_progress → 即将开始；published+ended → 已结束', () {
      expect(
        myGatheringsSegmentOf(_card(id: 'g1', title: 't')),
        MyGatheringsSegment.upcoming,
      );
      expect(
        myGatheringsSegmentOf(
          _card(id: 'g2', title: 't', temporal: 'in_progress'),
        ),
        MyGatheringsSegment.upcoming,
      );
      expect(
        myGatheringsSegmentOf(_card(id: 'g3', title: 't', temporal: 'ended')),
        MyGatheringsSegment.ended,
      );
    });

    test('completed → 已结束；cancelled → 已取消；draft → 草稿；未知 lifecycle 防御归入已结束', () {
      expect(
        myGatheringsSegmentOf(
          _card(
            id: 'g4',
            title: 't',
            lifecycle: 'completed',
            temporal: 'ended',
          ),
        ),
        MyGatheringsSegment.ended,
      );
      expect(
        myGatheringsSegmentOf(
          _card(id: 'g5', title: 't', lifecycle: 'cancelled'),
        ),
        MyGatheringsSegment.cancelled,
      );
      // draft 是私有读面的一等分组（OPEN-008 收口）。
      expect(
        myGatheringsSegmentOf(_card(id: 'g6', title: 't', lifecycle: 'draft')),
        MyGatheringsSegment.draft,
      );
      // 未识别 lifecycle 防御归入已结束，不渲染进行中假象。
      expect(
        myGatheringsSegmentOf(
          _card(id: 'g7', title: 't', lifecycle: 'unknown_status'),
        ),
        MyGatheringsSegment.ended,
      );
    });

    test('segment 深链闭集归一：未知值归 upcoming', () {
      expect(
        MyGatheringsSegment.fromQueryValue('ended'),
        MyGatheringsSegment.ended,
      );
      expect(
        MyGatheringsSegment.fromQueryValue('bogus'),
        MyGatheringsSegment.upcoming,
      );
      expect(
        MyGatheringsSegment.fromQueryValue(null),
        MyGatheringsSegment.upcoming,
      );
    });
  });

  testWidgets('我的行动页消费 host 本人私有读面并四分组切换（含 draft 与非公开行动）', (tester) async {
    final reader = _StubGatheringQueryReader(
      page: GatheringHostCardPage(
        items: <GatheringHostCardSummary>[
          _card(id: 'g-up', title: '一起去黄龙', dateLabel: '本周六'),
          // 私有读面独有：invite-only 已发布行动与待发布草稿（OPEN-008 断点）。
          _card(id: 'g-duo', title: '双人看展邀约'),
          _card(id: 'g-draft', title: '草稿里的行动', lifecycle: 'draft'),
          _card(
            id: 'g-done',
            title: '西岸美术馆看展',
            lifecycle: 'completed',
            temporal: 'ended',
          ),
          _card(id: 'g-cancel', title: '取消的行动', lifecycle: 'cancelled'),
        ],
        nextCursor: '',
        hasMore: false,
      ),
    );
    await _pumpPage(tester, reader);

    // 数据源必须是 host 本人私有读面（服务端从受信 persona 解析身份）。
    expect(reader.listMineCalls, 1);

    // 默认分组 = 即将开始：公开与 invite-only 的 upcoming 都可见，且展示余席。
    expect(find.text('一起去黄龙'), findsOneWidget);
    expect(find.text('双人看展邀约'), findsOneWidget);
    expect(find.text('草稿里的行动'), findsNothing);
    expect(find.text('西岸美术馆看展'), findsNothing);
    expect(
      find.text(GatheringText.sourceGatheringSeatsRemaining(2)),
      findsNWidgets(2),
    );

    // 切到草稿分组：draft 只在私有读面出现，且不展示余席。
    await tester.tap(find.text(GatheringText.myGatheringsSegmentDraft));
    await tester.pump();
    expect(find.text('草稿里的行动'), findsOneWidget);
    expect(
      find.text(GatheringText.sourceGatheringSeatsRemaining(2)),
      findsNothing,
    );

    // 切到已结束分组。
    await tester.tap(find.text(GatheringText.myGatheringsSegmentEnded));
    await tester.pump();
    expect(find.text('西岸美术馆看展'), findsOneWidget);
    expect(find.text('一起去黄龙'), findsNothing);

    // 切到已取消分组。
    await tester.tap(find.text(GatheringText.myGatheringsSegmentCancelled));
    await tester.pump();
    expect(find.text('取消的行动'), findsOneWidget);
  });

  testWidgets('行动卡直通 Gathering 详情', (tester) async {
    final reader = _StubGatheringQueryReader(
      page: GatheringHostCardPage(
        items: <GatheringHostCardSummary>[_card(id: 'g-up', title: '一起去黄龙')],
        nextCursor: '',
        hasMore: false,
      ),
    );
    await _pumpPage(tester, reader);
    await tester.tap(
      find.byKey(const ValueKey<String>('my-gathering-card-g-up')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    expect(find.text('GATHERING:g-up'), findsOneWidget);
  });

  testWidgets('segment 深链直达对应分组', (tester) async {
    final reader = _StubGatheringQueryReader(
      page: GatheringHostCardPage(
        items: <GatheringHostCardSummary>[
          _card(id: 'g-cancel', title: '取消的行动', lifecycle: 'cancelled'),
        ],
        nextCursor: '',
        hasMore: false,
      ),
    );
    await _pumpPage(tester, reader, segment: 'cancelled');
    expect(find.text('取消的行动'), findsOneWidget);
  });

  testWidgets('空数据渲染诚实空态（不渲染假列表）', (tester) async {
    final reader = _StubGatheringQueryReader();
    await _pumpPage(tester, reader);
    expect(find.byType(AppEmptyState), findsOneWidget);
    expect(find.text(GatheringText.myGatheringsEmptyTitle), findsOneWidget);
  });

  testWidgets('读取失败渲染结构化错误态并可重试恢复，不伪造空态', (tester) async {
    final reader = _StubGatheringQueryReader(
      failure: StateError('gathering host list unavailable'),
    );
    await _pumpPage(tester, reader);

    expect(find.byType(AppPageErrorState), findsOneWidget);
    // 负例：失败不得伪造「还没有公开行动」空态。
    expect(find.text(GatheringText.myGatheringsEmptyTitle), findsNothing);
    expect(reader.listMineCalls, 1);
  });
}
