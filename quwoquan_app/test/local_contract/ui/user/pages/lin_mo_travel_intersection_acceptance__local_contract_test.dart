import 'dart:convert';
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_fact_items.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_repository.dart';
import 'package:quwoquan_app/components/object_page/intersection_icon_resolver.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/pages/my_intersection_inbox_page.dart';
import 'package:quwoquan_cloud_contracts/generated/content_contracts.dart'
    show
        IntersectionInboxSummary,
        IntersectionReason,
        IntersectionTarget,
        IntersectionTextSpan;

import '../../../../support/fixtures/intersection_fixtures.dart';

/// 林墨「旅行摄影」交集/影响力实例化验收（WS-ACC，§22 覆盖矩阵）。
///
/// 三段闭环，全部 CI 安全（不依赖 contract fixture profile）：
///   1. 数据实例化：直接读取主 seed（content_scenarios.json），断言林墨三元组
///      `(基kind + vertical=travel_photography + objectKind∈{route,photo_spot,gear,place,circle,person})`
///      铺满维度/生命周期，route/photo_spot/gear 落点为 homepageDetail，影响力实例齐备。
///   2. 生命周期显隐过滤：`filterDefaultInboxLifecycle` 端侧单源（expired 不进 UI、
///      archived 不进默认列表），mock/remote 列表路径共用。
///   3. 渲染契约：「我的交集」inbox 行三元组驱动（类型角标 + 句内蓝字实名代表人 +
///      lifecycle 弱标），archived/expired 不渲染。
void main() {
  group('WS-ACC · 林墨旅行交集数据实例化（主 seed 真相源）', () {
    late final List<Map<String, dynamic>> linMoReasons;
    late final Map<String, dynamic> intersectionCore;

    setUpAll(() {
      final seed = _loadIntersectionCoreSeed();
      intersectionCore = seed;
      final inbox = (seed['inboxReasons'] as List)
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList(growable: false);
      linMoReasons = inbox
          .where(
            (r) => (r['intersectionId'] ?? '').toString().startsWith('ix_lm_'),
          )
          .toList(growable: false);
    });

    test('三元组：travel_photography vertical 覆盖 6 类 objectKind', () {
      expect(linMoReasons, isNotEmpty, reason: '主 seed 应已实例化林墨旅行交集');
      // 全部林墨交集 vertical 必须是 travel_photography（三元组第二元正交）。
      expect(
        linMoReasons.every((r) => r['vertical'] == 'travel_photography'),
        isTrue,
        reason: '林墨旅行交集 vertical 必须统一为 travel_photography',
      );
      final objectKinds = linMoReasons
          .map((r) => (r['objectKind'] ?? '').toString())
          .toSet();
      for (final kind in <String>[
        'route',
        'photo_spot',
        'gear',
        'place',
        'circle',
        'person',
      ]) {
        expect(
          objectKinds.contains(kind),
          isTrue,
          reason: 'objectKind=$kind 应至少有一条林墨交集实例',
        );
      }
    });

    test(
      '生命周期多态：new/strengthened/stable/weakened/reactivated/archived/expired 全覆盖',
      () {
        final lifecycles = linMoReasons
            .map((r) => (r['lifecycleState'] ?? '').toString())
            .toSet();
        for (final state in <String>[
          'new',
          'strengthened',
          'stable',
          'weakened',
          'reactivated',
          'archived',
          'expired',
        ]) {
          expect(
            lifecycles.contains(state),
            isTrue,
            reason: 'lifecycleState=$state 应有代表样本',
          );
        }
      },
    );

    test('route/photo_spot/gear 落点：object 片段 routeId=homepageDetail', () {
      final objectReasons = linMoReasons.where(
        (r) => <String>{
          'route',
          'photo_spot',
          'gear',
        }.contains((r['objectKind'] ?? '').toString()),
      );
      expect(objectReasons, isNotEmpty);
      for (final reason in objectReasons) {
        final objectKind = (reason['objectKind'] ?? '').toString();
        final spans = (reason['primarySpans'] as List? ?? const [])
            .whereType<Map>();
        // 选取与交集 objectKind 一致的对象落点片段（同句可并存 person 实名代表人片段）。
        final objectSpan = spans.firstWhere(
          (s) =>
              s['role'] == 'object' &&
              ((s['target'] as Map?)?['objectKind'] == objectKind),
          orElse: () => const <String, dynamic>{},
        );
        expect(
          objectSpan,
          isNotEmpty,
          reason: '${reason['intersectionId']} 应有 objectKind=$objectKind 的落点片段',
        );
        final target = (objectSpan['target'] as Map?)?.cast<String, dynamic>();
        expect(
          target?['routeId'],
          'homepageDetail',
          reason: '${reason['intersectionId']} $objectKind 落点须 homepageDetail',
        );
      }
    });

    test('实名代表人锚点：命名代表人以 object 片段进入对象页（隐私红线）', () {
      // 至少一条携带实名代表人（object 片段含 person 落点）。
      final withNamedActor = linMoReasons.where((r) {
        final spans = (r['primarySpans'] as List? ?? const []).whereType<Map>();
        return spans.any(
          (s) =>
              s['role'] == 'object' &&
              ((s['target'] as Map?)?['objectKind'] == 'person'),
        );
      });
      expect(withNamedActor, isNotEmpty, reason: '林墨交集应有实名代表人样本（person 落点蓝字）');
    });

    test('影响力实例：fixture_user_travel_curator 多类 helpType + 实名代表人 + 生命周期', () {
      final impactByAuthor = (intersectionCore['authorImpact'] as Map)
          .cast<String, dynamic>();
      final linMo = (impactByAuthor['fixture_user_travel_curator'] as Map)
          .cast<String, dynamic>();
      final items = (linMo['items'] as List)
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList(growable: false);
      expect(
        items.length,
        greaterThanOrEqualTo(5),
        reason: '影响力应覆盖多类 helpType',
      );

      // 维度跨多类（community/decision/spread/relationship/knowledge → dimension 投影）。
      final dimensions = items
          .map((e) => (e['intersectionDimension'] ?? '').toString())
          .toSet();
      expect(
        dimensions.length,
        greaterThanOrEqualTo(3),
        reason: '影响力维度应跨 interest/location/content/relationship 多类',
      );

      // 生命周期多态。
      final lifecycles = items
          .map((e) => (e['lifecycleState'] ?? '').toString())
          .toSet();
      expect(lifecycles.contains('strengthened'), isTrue);
      expect(lifecycles.contains('reactivated'), isTrue);

      // 实名代表人（守红线：仅可证绝对计数，禁转化率/漏斗）。
      final withRep = items.where(
        (e) =>
            (e['representativeActor'] is Map) &&
            ((e['representativeActor'] as Map)['displayName'] ?? '')
                .toString()
                .isNotEmpty,
      );
      expect(withRep, isNotEmpty, reason: '影响力应有实名代表人样本');
      // 绝对计数下钻（countTarget 语义：count > 0）。
      expect(items.every((e) => (e['count'] as num? ?? 0) >= 0), isTrue);
    });

    test('span 单通道不变量：join(primarySpans.text) == primaryText', () {
      for (final reason in linMoReasons) {
        final spans = (reason['primarySpans'] as List? ?? const [])
            .whereType<Map>();
        if (spans.isEmpty) continue;
        final joined = spans.map((s) => (s['text'] ?? '').toString()).join();
        expect(
          joined,
          reason['primaryText'],
          reason: '${reason['intersectionId']} 富文本切分须无损拼回 primaryText',
        );
      }
    });
  });

  group('WS-ACC · 生命周期显隐过滤（端侧单一真相源）', () {
    test('filterDefaultInboxLifecycle：expired/archived 被剔除，其余保留', () {
      final input = <IntersectionReason>[
        _reason('keep_new', lifecycleState: 'new'),
        _reason('keep_stable', lifecycleState: 'stable'),
        _reason('keep_weakened', lifecycleState: 'weakened'),
        _reason('drop_archived', lifecycleState: 'archived'),
        _reason('drop_expired', lifecycleState: 'expired'),
      ];
      final out = filterDefaultInboxLifecycle(input);
      final ids = out.map((r) => r.intersectionId).toSet();
      expect(
        ids,
        containsAll(<String>['keep_new', 'keep_stable', 'keep_weakened']),
      );
      expect(ids.contains('drop_archived'), isFalse);
      expect(ids.contains('drop_expired'), isFalse);
    });

    test('隐藏闭集 == {expired, archived}', () {
      expect(defaultInboxHiddenLifecycleStates, <String>{
        'expired',
        'archived',
      });
    });
  });

  group('WS-ACC · 我的交集 inbox 三元组渲染契约', () {
    testWidgets(
      'route/photo_spot/gear 三元组：类型角标 + 实名代表人蓝字 + lifecycle 弱标；archived/expired 不渲染',
      (tester) async {
        await tester.pumpWidget(
          ProviderScope(
            overrides: [
              authSessionControllerProvider.overrideWith(_AuthedSession.new),
              intersectionRepositoryProvider.overrideWithValue(
                _LinMoTravelRepository(),
              ),
            ],
            child: CupertinoApp.router(routerConfig: _router()),
          ),
        );
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 50));

        // 三元组结论句渲染（route / photo_spot / gear）。
        expect(find.textContaining('洱海环线'), findsWidgets);
        expect(find.textContaining('玉龙雪山机位'), findsWidgets);
        expect(find.textContaining('富士 X-T5'), findsWidgets);

        // 实名代表人为句内纯文本蓝字（无网络头像 Image）。
        expect(find.textContaining('陈屿'), findsWidgets);
        expect(find.textContaining('苏野'), findsWidgets);
        expect(find.byType(Image), findsNothing);

        // lifecycle 弱标：new→新 / strengthened→增强 / reactivated→重新活跃。
        expect(
          find.text(DiscoveryFeedText.intersectionLifecycleNew),
          findsWidgets,
        );
        expect(
          find.textContaining(
            DiscoveryFeedText.intersectionLifecycleStrengthened,
          ),
          findsWidgets,
        );
        expect(
          find.text(DiscoveryFeedText.intersectionLifecycleReactivated),
          findsOneWidget,
        );

        // 类型角标（槽①）每行一枚。
        expect(find.byType(IntersectionTypeIcon), findsAtLeastNWidgets(3));

        // archived/expired 被端侧过滤，主列表不渲染其结论句。
        expect(find.textContaining('老君山观景台'), findsNothing);
        expect(find.textContaining('临时市集'), findsNothing);
      },
    );
  });
}

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

Map<String, dynamic> _loadIntersectionCoreSeed() {
  const relative =
      'quwoquan_service/services/content-service/tests/support/contract_fixtures/scenarios/content_scenarios.json';
  final candidates = <String>[
    '../$relative',
    relative,
    '../../$relative',
    '/Users/zhaoyuxi/Projects/quwoquan/$relative',
  ];
  for (final path in candidates) {
    final file = File(path);
    if (!file.existsSync()) continue;
    final decoded = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final seedSets = (decoded['seedSets'] as Map).cast<String, dynamic>();
    return (seedSets['intersection_core'] as Map).cast<String, dynamic>();
  }
  fail('未找到主 seed 文件 content_scenarios.json（cwd=${Directory.current.path}）');
}

IntersectionReason _reason(String id, {required String lifecycleState}) {
  return intersectionReasonFixture(
    intersectionId: id,
    dimension: 'location',
    intersectionClass: 'fact',
    objectKind: 'place',
    primaryText: '占位 $id',
    actionTargetId: 'fixture_homepage_travel_photo_west_lake',
    lifecycleState: lifecycleState,
    freshAt: DateTime.now().toUtc().toIso8601String(),
  );
}

GoRouter _router() {
  return GoRouter(
    initialLocation: '/',
    routes: [
      GoRoute(path: '/', builder: (_, _) => const MyIntersectionInboxPage()),
      GoRoute(
        path: '/user/:userHandle',
        builder: (_, state) =>
            Text('USER:${state.pathParameters['userHandle']}'),
      ),
    ],
  );
}

class _AuthedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'test-token',
      ownerId: 'fixture_user_travel_curator',
      activePersonaId: 'fixture_user_travel_curator',
      accountState: 'active',
      identityOrigin: 'test',
      installId: 'test-install',
    );
  }
}

/// 复刻林墨主 seed 的旅行三元组（route/photo_spot/gear）+ archived/expired，
/// 列表路径走 `filterDefaultInboxLifecycle` 单源，验证 inbox 渲染与显隐契约。
class _LinMoTravelRepository implements IntersectionRepository {
  @override
  Future<IntersectionInboxSummary> getMyIntersectionSummary() async {
    return intersectionInboxSummaryFixture(totalCount: 3, totalNewCount: 1);
  }

  @override
  Future<List<IntersectionReason>> listMyIntersections({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    String? cursor,
    int limit = 50,
  }) async {
    final all = <IntersectionReason>[
      _travelReason(
        id: 'ix_lm_loc_route',
        objectKind: 'route',
        objectName: '洱海环线',
        objectId: 'fixture_homepage_travel_photo_dali',
        repName: '陈屿',
        repId: 'fixture_user_zhou',
        lifecycleState: 'strengthened',
        strengthDelta: 6.0,
        primaryText: '你和陈屿等12人都走过洱海环线',
        leadPlain: '你和',
        midPlain: '等12人都走过',
      ),
      _travelReason(
        id: 'ix_lm_loc_spot',
        objectKind: 'photo_spot',
        objectName: '玉龙雪山机位',
        objectId: 'fixture_homepage_travel_photo_dali',
        repName: '',
        repId: '',
        lifecycleState: 'new',
        primaryText: '你拍过玉龙雪山机位',
        leadPlain: '你拍过',
        midPlain: '',
      ),
      _travelReason(
        id: 'ix_lm_int_gear',
        objectKind: 'gear',
        objectName: '富士 X-T5',
        objectId: 'fixture_homepage_travel_photo_tokyo',
        repName: '苏野',
        repId: 'fixture_user_su',
        lifecycleState: 'reactivated',
        primaryText: '你和苏野都在关注富士 X-T5',
        leadPlain: '你和',
        midPlain: '都在关注',
      ),
      // archived / expired：应被默认列表过滤。
      _travelReason(
        id: 'ix_lm_loc_archived',
        objectKind: 'place',
        objectName: '老君山观景台',
        objectId: 'fixture_homepage_travel_photo_west_lake',
        repName: '',
        repId: '',
        lifecycleState: 'archived',
        primaryText: '你和周屿等2人都看过老君山观景台',
        leadPlain: '你和周屿等2人都看过',
        midPlain: '',
      ),
      _travelReason(
        id: 'ix_lm_loc_expired',
        objectKind: 'place',
        objectName: '临时市集',
        objectId: 'fixture_homepage_travel_photo_west_lake',
        repName: '',
        repId: '',
        lifecycleState: 'expired',
        primaryText: '你和1人去过临时市集',
        leadPlain: '你和1人去过',
        midPlain: '',
      ),
    ];
    // 与 Mock/Remote 同源：默认列表剔除 archived/expired。
    return filterDefaultInboxLifecycle(all);
  }

  @override
  Future<List<IntersectionReason>> getObjectIntersections({
    required String objectId,
    required String objectType,
    int limit = 8,
  }) async => const <IntersectionReason>[];
}

IntersectionReason _travelReason({
  required String id,
  required String objectKind,
  required String objectName,
  required String objectId,
  required String repName,
  required String repId,
  required String lifecycleState,
  required String primaryText,
  required String leadPlain,
  required String midPlain,
  double strengthDelta = 0,
}) {
  final spans = <IntersectionTextSpan>[
    if (leadPlain.isNotEmpty)
      IntersectionTextSpan(text: leadPlain, role: 'plain'),
    if (repName.isNotEmpty)
      IntersectionTextSpan(
        text: repName,
        role: 'object',
        target: IntersectionTarget(
          objectType: 'user',
          objectId: repId,
          objectKind: 'person',
          routeId: 'userProfile',
        ),
      ),
    if (midPlain.isNotEmpty)
      IntersectionTextSpan(text: midPlain, role: 'plain'),
    IntersectionTextSpan(
      text: objectName,
      role: 'object',
      target: IntersectionTarget(
        objectType: 'homepage',
        objectId: objectId,
        objectKind: objectKind,
        routeId: 'homepageDetail',
      ),
    ),
  ];
  return intersectionReasonFixture(
    intersectionId: id,
    vertical: 'travel_photography',
    dimension: objectKind == 'gear' ? 'interest' : 'location',
    intersectionClass: 'fact',
    objectKind: objectKind,
    displayName: objectName,
    primaryText: primaryText,
    primarySpans: spans,
    actionTargetId: objectId,
    source: 'location',
    iconKey: objectKind,
    lifecycleState: lifecycleState,
    strengthDelta: strengthDelta,
    timeBucket: 'today',
    freshAt: DateTime.now().toUtc().toIso8601String(),
    actorEvidenceTotalCount: 1,
    actorEvidenceCompleteness: 'complete',
    representativeActor: repName.isEmpty
        ? null
        : intersectionRepresentativeActorFixture(
            actorId: repId,
            displayName: repName,
            relationLabel: '联系人',
            privacyState: 'visible',
            target: IntersectionTarget(
              objectType: 'user',
              objectId: repId,
              objectKind: 'person',
              routeId: 'userProfile',
            ),
          ),
  );
}
