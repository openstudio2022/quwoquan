// spec_ref: specs/feature-tree/circle-community/gathering-coordination/offline-actions-discovery-tab/spec.md#req-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/offline-actions-discovery-tab/spec.md#gwt-001
//
// 线下行动与发现（底栏「行动」tab）页面契约：
// - 游客可浏览：标题、兴趣配对与发起行动入口常驻；账号态卡不渲染，
//   以「登录后查看」诚实入口替代（不伪造空数据）。
// - 登录态：交集收件箱卡与「我的行动」入口渲染。
// - 兴趣配对入口跳 /interest-match（游客同样可达）。
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_actions_discovery_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/my_gatherings_entry_card.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';

const _intersectionInboxKey = ValueKey<String>(
  'gathering-intersection-inbox-test-slot',
);

final class _StubGatheringQueryReader implements GatheringQueryReader {
  @override
  Future<GatheringHostCardPage> listByHost(
    GatheringByHostListQuery query,
  ) async => GatheringHostCardPage.empty;

  @override
  Future<GatheringHostCardPage> listMine(GatheringMineListQuery query) async =>
      GatheringHostCardPage.empty;

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
      refreshToken: 'test-refresh',
      ownerId: 'test-user',
      activePersonaId: 'test-persona',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

List<Override> _boundaryOverrides({required bool authenticated}) {
  return <Override>[
    ...sealedCloudBoundaryOverrides(),
    if (authenticated)
      authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
    gatheringQueryReaderProvider.overrideWithValue(_StubGatheringQueryReader()),
    intersectionRepositoryProvider.overrideWithValue(
      InMemoryIntersectionRepository(),
    ),
  ];
}

Future<void> _pumpPage(
  WidgetTester tester, {
  required bool authenticated,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: _boundaryOverrides(authenticated: authenticated),
      child: CupertinoApp.router(
        routerConfig: GoRouter(
          initialLocation: '/',
          routes: <GoRoute>[
            GoRoute(
              path: '/',
              builder: (_, _) => const CupertinoPageScaffold(
                child: GatheringActionsDiscoveryPage(
                  buildIntersectionInbox: _buildIntersectionInbox,
                ),
              ),
            ),
            GoRoute(
              path: '/interest-match',
              builder: (_, _) => const Text('INTEREST_MATCH'),
            ),
          ],
        ),
      ),
    ),
  );
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 50));
}

void main() {
  testWidgets('游客可浏览：标题与公共入口常驻，账号态卡以诚实登录入口替代', (tester) async {
    await _pumpPage(tester, authenticated: false);

    expect(find.byKey(GatheringActionsDiscoveryPage.pageKey), findsOneWidget);
    expect(
      find.text(AppConceptConstants.offlineActionsPageTitle),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('actions-discover-interest')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('actions-create-gathering')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('actions-guest-login')),
      findsOneWidget,
    );
    // 诚实降级：游客不渲染账号态数据卡（不得伪造空数据冒充真实读面）。
    expect(find.byKey(_intersectionInboxKey), findsNothing);
    expect(find.byKey(MyGatheringsEntryCard.cardKey), findsNothing);
  });

  testWidgets('登录态渲染交集收件箱与我的行动入口', (tester) async {
    await _pumpPage(tester, authenticated: true);

    expect(find.byKey(_intersectionInboxKey), findsOneWidget);
    expect(find.byKey(MyGatheringsEntryCard.cardKey), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('actions-guest-login')),
      findsNothing,
    );
  });

  testWidgets('兴趣配对入口游客可达（无登录门）', (tester) async {
    await _pumpPage(tester, authenticated: false);

    await tester.tap(
      find.byKey(const ValueKey<String>('actions-discover-interest')),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.text('INTEREST_MATCH'), findsOneWidget);
  });

  testWidgets('页面文案来自唯一文案常量入口', (tester) async {
    await _pumpPage(tester, authenticated: false);

    expect(find.text(GatheringText.actionsDiscoverySubtitle), findsOneWidget);
    expect(
      find.text(GatheringText.actionsDiscoverInterestTitle),
      findsOneWidget,
    );
    expect(find.text(GatheringText.actionsCreateEntryTitle), findsOneWidget);
    expect(find.text(GatheringText.actionsGuestIntroTitle), findsOneWidget);
  });
}

Widget _buildIntersectionInbox({required bool isDark}) =>
    const SizedBox(key: _intersectionInboxKey);
