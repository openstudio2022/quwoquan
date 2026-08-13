import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/gathering_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/shell/navigation/route_unavailable_state.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart'
    show GatheringAdmissionPolicy, GatheringAudiencePolicy;
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_create_page.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_route_hosts.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

// 生产 composer 契约：`gatheringCreateInitialValueProvider` 不再 fail-closed
// throw，而是把「当前 persona + 交集导航上下文」组合成可提交的创建初始值；
// persona host 授权凭证使用 canonical 自引用（persona:{id}:self + 快照版本），
// 服务端仍会经 owner 重新评估。创建页不得暴露任何内部 ID / 授权 / ISO 字段。

GatheringCreateNavigationRequest _navigationRequest() {
  return const GatheringCreateNavigationRequest(
    actionKey: 'startGathering',
    actionLabel: '发起聚集',
    sourceRefs: <GatheringCreateSourceReference>[
      // server TargetReader 可导航：place + homepageDetail。
      GatheringCreateSourceReference(
        sourceRef: 'coWishlistedEntity',
        objectId: 'homepage-1',
        objectKind: 'place',
        routeId: 'homepageDetail',
      ),
      // server TargetReader 不可导航：tag 无对应目标读取，必须被过滤。
      GatheringCreateSourceReference(
        sourceRef: 'sharedTagSample',
        objectId: 'tag-1',
        objectKind: 'tag',
        routeId: 'myIntersections',
      ),
    ],
    targetObject: GatheringCreateTargetObject(
      objectId: 'homepage-1',
      objectKind: 'place',
      objectName: '黄龙雪山',
      routeId: 'homepageDetail',
    ),
    intersection: GatheringCreateIntersectionContext(
      intersectionId: 'intersection-1',
      dimension: 'place',
      intersectionClass: 'fact',
    ),
    evidence: GatheringCreateEvidenceContext(
      evidenceId: 'evidence-1',
      sourceRef: 'coWishlistedEntity',
      tagRefs: <String>[],
    ),
    referralSource: ReferralSource.myIntersections,
  );
}

Future<InMemoryGatheringPort> _pumpProductionCreateHost(
  WidgetTester tester, {
  GatheringCreateNavigationRequest? navigationRequest,
  String personaId = 'persona-1',
  int personaSnapshotVersion = 7,
}) async {
  final port = InMemoryGatheringPort();
  await tester.binding.setSurfaceSize(const Size(430, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        authSessionControllerProvider.overrideWith(_AuthenticatedSession.new),
        activePersonaContextProvider.overrideWith(
          (_) async => ActivePersonaContextViewData.fallback(
            personaId: personaId,
            ownerUserId: 'owner-1',
            displayName: '测试用户',
            avatarUrl: '',
            personaSnapshotVersion: personaSnapshotVersion,
          ),
        ),
        ...gatheringBoundaryOverrides(port),
      ],
      child: CupertinoApp(
        home: GatheringCreatePageRouteHost(
          navigationRequest: navigationRequest,
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return port;
}

void main() {
  group('Gathering create production composer local_contract', () {
    testWidgets('生产装配下创建页可渲染并以 canonical persona 授权提交', (tester) async {
      final port = await _pumpProductionCreateHost(
        tester,
        navigationRequest: _navigationRequest(),
      );

      expect(find.byType(RouteUnavailableState), findsNothing);
      expect(find.byKey(GatheringCreatePage.viewKey), findsOneWidget);

      // 交集上下文预填：标题与公开地点来自目标对象。
      expect(find.text('一起去黄龙雪山'), findsOneWidget);

      // 补齐必填的活动说明与准确集合点后提交。
      await tester.enterText(
        find
            .widgetWithText(
              CupertinoTextField,
              GatheringText.createSummaryPlaceholder,
            )
            .first,
        '一起去雪山徒步，白天集合。',
      );
      final exactPointField = find.widgetWithText(
        CupertinoTextField,
        GatheringText.createExactMeetingPointLabel,
      );
      await tester.enterText(exactPointField.first, '东门售票处');
      await tester.ensureVisible(find.byKey(GatheringCreatePage.submitKey));
      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.pumpAndSettle();

      expect(port.createCalls, 1);
      final create = port.lastCreate!;
      expect(create.host.subjectId, 'persona-1');
      expect(create.host.authorityEvidenceRef, 'persona:persona-1:self');
      expect(create.host.authorityVersion, 7);
      expect(create.creatorParticipates, isTrue);
      expect(create.policy.riskControlPolicyRef, 'risk/standard-day-public-v1');
      expect(create.schedule.timezone, 'Asia/Shanghai');
      expect(create.schedule.endAt.isAfter(create.schedule.startAt), isTrue);

      // sourceRefs 只携带 server TargetReader 可导航的组合，不可导航引用被过滤。
      expect(create.purpose.sourceRefs, hasLength(1));
      final source = create.purpose.sourceRefs.single;
      expect(source.objectRef.objectTypeRef, 'place');
      expect(source.objectRef.objectId, 'homepage-1');
      expect(source.routeId, 'homepageDetail');
      expect(source.sourceDigest, 'intersection:coWishlistedEntity');
    });

    testWidgets('双人邀约预设：容量 2 + 邀请制 + 不套对象名标题', (tester) async {
      const duoRequest = GatheringCreateNavigationRequest(
        actionKey: 'startGathering',
        actionLabel: '邀 TA 同行',
        sourceRefs: <GatheringCreateSourceReference>[
          GatheringCreateSourceReference(
            sourceRef: 'coWishlistedEntity',
            objectId: 'homepage-1',
            objectKind: 'place',
            routeId: 'homepageDetail',
          ),
        ],
        // 他人主页交集卡发起：target 是人（受邀者上下文）。
        targetObject: GatheringCreateTargetObject(
          objectId: 'persona-invitee',
          objectKind: 'person',
          objectName: '小雅',
          routeId: 'userProfile',
        ),
        intersection: GatheringCreateIntersectionContext(
          intersectionId: 'intersection-duo',
          dimension: 'place',
          intersectionClass: 'fact',
        ),
        evidence: GatheringCreateEvidenceContext(
          evidenceId: 'evidence-duo',
          sourceRef: 'coWishlistedEntity',
          tagRefs: <String>[],
        ),
        referralSource: ReferralSource.myIntersections,
        inviteePersonaId: 'persona-invitee',
        inviteeDisplayName: '小雅',
      );
      final port = await _pumpProductionCreateHost(
        tester,
        navigationRequest: duoRequest,
      );

      expect(find.byType(RouteUnavailableState), findsNothing);
      // 目标是人：不套「一起去{对象名}」模板。
      expect(find.text('一起去小雅'), findsNothing);

      // 补齐必填项后提交，断言双人安全预设进入创建输入。
      await tester.enterText(
        find
            .widgetWithText(
              CupertinoTextField,
              GatheringText.createTitlePlaceholder,
            )
            .first,
        '周末一起去森林公园',
      );
      await tester.enterText(
        find
            .widgetWithText(
              CupertinoTextField,
              GatheringText.createSummaryPlaceholder,
            )
            .first,
        '同好双人徒步，白天集合。',
      );
      // 目标是人：公开地点无预填，物理场地两级地点均需填写。
      final coarsePlaceField = find.widgetWithText(
        CupertinoTextField,
        GatheringText.createCoarsePlaceLabel,
      );
      await tester.enterText(coarsePlaceField.first, '森林公园');
      final exactPointField = find.widgetWithText(
        CupertinoTextField,
        GatheringText.createExactMeetingPointLabel,
      );
      await tester.enterText(exactPointField.first, '公园东门');
      await tester.ensureVisible(find.byKey(GatheringCreatePage.submitKey));
      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.pumpAndSettle();

      expect(port.createCalls, 1);
      final create = port.lastCreate!;
      expect(create.policy.maxParticipants, 2);
      expect(
        create.policy.admission,
        GatheringAdmissionPolicy.inviteOnly,
      );
      expect(
        create.policy.audience,
        GatheringAudiencePolicy.inviteOnly,
      );
    });

    testWidgets('表单不暴露内部 ID、授权凭证与 ISO 时间文本', (tester) async {
      await _pumpProductionCreateHost(
        tester,
        navigationRequest: _navigationRequest(),
      );

      expect(find.textContaining('persona:'), findsNothing);
      expect(find.text(GatheringText.createAuthorityEvidenceLabel), findsNothing);
      expect(find.text(GatheringText.createAuthorityVersionLabel), findsNothing);
      expect(find.text(GatheringText.createHostSubjectIdLabel), findsNothing);
      expect(find.text(GatheringText.createRiskControlPolicyLabel), findsNothing);
      expect(find.textContaining('risk/'), findsNothing);
      final isoPattern = RegExp(r'\d{4}-\d{2}-\d{2}T');
      expect(
        find.byWidgetPredicate(
          (widget) => widget is Text && isoPattern.hasMatch(widget.data ?? ''),
        ),
        findsNothing,
      );
    });

    testWidgets('无导航上下文时创建页仍可用且不预填任何引用', (tester) async {
      final port = await _pumpProductionCreateHost(tester);

      expect(find.byType(RouteUnavailableState), findsNothing);
      expect(find.byKey(GatheringCreatePage.viewKey), findsOneWidget);

      await tester.enterText(
        find
            .widgetWithText(
              CupertinoTextField,
              GatheringText.createTitlePlaceholder,
            )
            .first,
        '周末骑行',
      );
      await tester.enterText(
        find
            .widgetWithText(
              CupertinoTextField,
              GatheringText.createSummaryPlaceholder,
            )
            .first,
        '沿滨江骑到渡口，慢速友好。',
      );
      final coarseField = find.widgetWithText(
        CupertinoTextField,
        GatheringText.createCoarsePlaceLabel,
      );
      await tester.enterText(coarseField.first, '滨江大道');
      final exactPointField = find.widgetWithText(
        CupertinoTextField,
        GatheringText.createExactMeetingPointLabel,
      );
      await tester.enterText(exactPointField.first, '3 号门');
      await tester.ensureVisible(find.byKey(GatheringCreatePage.submitKey));
      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.pumpAndSettle();

      expect(port.createCalls, 1);
      expect(port.lastCreate!.purpose.sourceRefs, isEmpty);
    });

    testWidgets('persona 上下文与会话身份不一致时 fail-closed 到 RouteUnavailable', (
      tester,
    ) async {
      await _pumpProductionCreateHost(tester, personaId: 'persona-other');

      expect(find.byType(RouteUnavailableState), findsOneWidget);
      expect(find.byKey(GatheringCreatePage.viewKey), findsNothing);
    });
  });
}

final class _AuthenticatedSession extends AuthSessionController {
  @override
  AuthSessionState build() {
    return const AuthSessionState(
      status: AuthSessionStatus.authenticated,
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
      ownerId: 'owner-1',
      activePersonaId: 'persona-1',
      accountState: 'active',
      identityOrigin: 'phone',
      installId: 'install-1',
    );
  }
}
