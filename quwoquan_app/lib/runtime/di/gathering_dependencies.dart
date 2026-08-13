import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/circle_dependencies.dart';
import 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart'
    as gathering_domain;
import 'package:quwoquan_app/service/recommendation_service/recommendation/recommendation_feature_profile_view/application/public/gathering_create_navigation_request.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

typedef GatheringCreateBootstrapRequest = ({
  String activePersonaId,
  GatheringCreateNavigationRequest? navigationRequest,
});

/// persona host 的授权凭证是 canonical 自引用（user-service persona owner 合同：
/// `persona:{id}:self` + persona 快照版本）。服务端创建/发布时仍会经 owner
/// 重新评估授权，端侧只声明引用，不伪造治理证据。
final gatheringCreateInitialValueProvider =
    FutureProvider.family<
      GatheringCreateInitialValue,
      GatheringCreateBootstrapRequest
    >((ref, request) async {
      final personaId = request.activePersonaId.trim();
      if (personaId.isEmpty) {
        throw _gatheringCompositionFailure(
          semanticReason: 'gathering_create_identity_unavailable',
          port: 'AuthSession.activePersonaId',
        );
      }
      final persona = await ref.watch(activePersonaContextProvider.future);
      if (persona.personaId.trim() != personaId ||
          persona.personaSnapshotVersion <= 0) {
        throw _gatheringCompositionFailure(
          semanticReason: 'gathering_host_authority_unavailable',
          port: 'PersonaQuery.getActivePersonaContext',
        );
      }
      final navigation = request.navigationRequest;
      final targetName = navigation?.targetObject.objectName.trim() ?? '';
      final targetRouteId = navigation?.targetObject.routeId.trim() ?? '';
      // 双人邀约（1对1 同好邀约）：从人对人交集发起时收紧安全默认——
      // 容量 2、邀请制、不公开列出；用户在创建页仍可改。
      final duo = navigation?.isDuoInvitation ?? false;
      final startAt = _defaultStartAt(DateTime.now());
      return GatheringCreateInitialValue(
        host: gathering_domain.GatheringHostInput(
          subjectKind: gathering_domain.GatheringHostSubjectKind.persona,
          subjectId: personaId,
          authorityEvidenceRef: 'persona:$personaId:self',
          authorityVersion: persona.personaSnapshotVersion,
        ),
        creatorParticipates: true,
        purpose: gathering_domain.GatheringPurposeDraft(
          // 目标是人（双人邀约）时不套「一起去{对象名}」模板，由发起者自拟。
          title: targetName.isEmpty || targetRouteId == 'userProfile'
              ? ''
              : '一起去$targetName',
          summary: '',
          sourceRefs: _navigableSourceRefs(navigation),
        ),
        schedule: gathering_domain.GatheringScheduleDraft(
          timezone: 'Asia/Shanghai',
          startAt: startAt,
          endAt: startAt.add(const Duration(hours: 2)),
        ),
        place: gathering_domain.GatheringPlaceDraft(
          mode: gathering_domain.GatheringPlaceMode.physical,
          coarsePlaceLabel: targetRouteId == 'homepageDetail' ? targetName : '',
          exactMeetingPoint: '',
          onlineLocationRef: '',
        ),
        policy: gathering_domain.GatheringPolicyDraft(
          audience: duo
              ? gathering_domain.GatheringAudiencePolicy.inviteOnly
              : gathering_domain.GatheringAudiencePolicy.public,
          admission: duo
              ? gathering_domain.GatheringAdmissionPolicy.inviteOnly
              : gathering_domain.GatheringAdmissionPolicy.approval,
          maxParticipants: duo ? 2 : 4,
          disclosure: const gathering_domain.GatheringDisclosurePolicyDraft(
            time: gathering_domain.GatheringTimeDisclosure.exact,
            place: gathering_domain.GatheringPlaceDisclosure.afterJoin,
            roster: gathering_domain.GatheringRosterDisclosure.countOnly,
          ),
          riskControlPolicyRef: 'risk/standard-day-public-v1',
        ),
      );
    });

/// 默认时间：明天（当前时刻已过 12:00 则后天）14:00 起，时长 2 小时——
/// 对齐「白天、公共场所」的安全默认模板；用户在创建页可改。
DateTime _defaultStartAt(DateTime now) {
  final daysAhead = now.hour >= 12 ? 2 : 1;
  final day = now.add(Duration(days: daysAhead));
  return DateTime(day.year, day.month, day.day, 14);
}

/// 服务端可导航目标真相源：circle TargetReader.RequireNavigable 只接受这些
/// (objectKind, routeId) 组合；此处只做 UX 预过滤，不可导航的引用直接不携带，
/// 避免整个创建请求 fail-closed。
const Map<String, String> _navigableSourceRouteByKind = <String, String>{
  'circle': 'circleDetail',
  'content': 'workBrowser',
  'person': 'userProfile',
  'school': 'homepageDetail',
  'place': 'homepageDetail',
  'enterprise': 'homepageDetail',
  'route': 'homepageDetail',
  'photo_spot': 'homepageDetail',
  'gear': 'homepageDetail',
  'homepage': 'homepageDetail',
};

List<gathering_domain.GatheringSourceRef> _navigableSourceRefs(
  GatheringCreateNavigationRequest? navigation,
) {
  if (navigation == null) {
    return const <gathering_domain.GatheringSourceRef>[];
  }
  final refs = <gathering_domain.GatheringSourceRef>[];
  for (final source in navigation.sourceRefs) {
    final objectKind = source.objectKind.trim();
    final objectId = source.objectId.trim();
    final routeId = source.routeId.trim();
    if (objectId.isEmpty ||
        _navigableSourceRouteByKind[objectKind] != routeId) {
      continue;
    }
    final provenance = source.sourceRef.trim().isEmpty
        ? navigation.actionKey.trim()
        : source.sourceRef.trim();
    refs.add(
      gathering_domain.GatheringSourceRef(
        objectRef: gathering_domain.GatheringCanonicalObjectRef(
          objectTypeRef: objectKind,
          objectId: objectId,
        ),
        routeId: routeId,
        sourceDigest: 'intersection:$provenance',
      ),
    );
  }
  return refs;
}

RuntimeFailure _gatheringCompositionFailure({
  required String semanticReason,
  required String port,
}) {
  return RuntimeFailure(
    code: RuntimeFailureCodes.appSystemUnknownError,
    semanticReason: semanticReason,
    origin: RuntimeFailureOrigin.environment,
    kind: RuntimeFailureKind.unavailable,
    nature: RuntimeFailureNature.permanent,
    location: const RuntimeFailureLocation(
      businessObject: 'circle.gathering',
      functionModule: 'gathering_dependencies',
    ),
    context: RuntimeFailureContext(
      attributes: <RuntimeContextAttribute>[
        RuntimeContextAttribute(key: 'port', value: port),
      ],
    ),
    recovery: const RuntimeRecoveryDirective(
      action: 'surface',
      disruptionLevel: 'fullPage',
    ),
  );
}

CloudOperationInvocationContext _gatheringInvocationContext(
  Ref ref, {
  required AppUiSurface surface,
  required String clientPageId,
  String? idempotencyKey,
}) {
  final accountId = ref.read(resolvedOwnerUserIdProvider).trim();
  final persona = ref.read(activePersonaContextProvider).asData?.value;
  final personaId = persona?.personaId.trim() ?? '';
  return CloudOperationInvocationContext(
    surfaceId: surface.id,
    clientPageId: clientPageId,
    routeId: surface.routeId,
    actor: CloudOperationActorContext(
      accountId: accountId.isEmpty ? null : accountId,
      personaId: personaId.isEmpty ? null : personaId,
    ),
    idempotencyKey: idempotencyKey,
  );
}

AppUiSurface _gatheringSurfaceForPageId(String clientPageId) {
  return switch (clientPageId) {
    CircleRequestPageIds.createGatheringDraft ||
    CircleRequestPageIds.publishGathering => AppUiSurfaces.gatheringCreate,
    // 来源对象公开行动读面：消费面是实体主页「近期公开行动」区块。
    CircleRequestPageIds.listGatheringsBySource => AppUiSurfaces.homepageDetail,
    // Host 公开行动读面：消费面是我的主页「我的行动」入口与分组页（REQ-008）。
    CircleRequestPageIds.listGatheringsByHost => AppUiSurfaces.myGatherings,
    _ => AppUiSurfaces.gatheringDetail,
  };
}

T _gatheringPort<T>(Ref ref, CircleProductionAdapter adapter) {
  return CircleProductionComposition.generatedAdapter<T>(
    adapter,
    client: ref.watch(generatedCloudOperationClientProvider),
    invocationContext: (String clientPageId, {String? idempotencyKey}) =>
        _gatheringInvocationContext(
          ref,
          surface: _gatheringSurfaceForPageId(clientPageId),
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
        ),
  );
}

/// Production 装配 generated Gathering command adapter。
final gatheringCommandWriterProvider = Provider<GatheringCommandWriter>(
  (ref) => _gatheringPort(ref, CircleProductionAdapter.gathering),
);

/// Production 装配 generated Gathering query adapter。
final gatheringQueryReaderProvider = Provider<GatheringQueryReader>(
  (ref) => _gatheringPort(ref, CircleProductionAdapter.gathering),
);
