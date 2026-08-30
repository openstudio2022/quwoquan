// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-012
/// 受管 Gamma Gathering 的 production Remote 名额提醒 runner。
///
/// 当前不登记 readiness_case：App 可证明 typed command、同意图重放、公开详情
/// readback 不产生 Participation/席位变化，但公开合同尚未暴露本人
/// AvailabilityWatch 的 active/version owner readback；该事实仍由 Circle service 的
/// real-Mongo API contract 证明，不能由 App 端推测。
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/adapters/gathering_remote.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/adapters/gathering_plan_remote.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';
import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

import 'package:quwoquan_app/service/circle_service/circle_management/gathering_plan/adapters/gathering_board_plan_reader.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

void main() {
  test('production Remote creates one availability watch without Participation or admission mutation', () async {
    final inputs = _GatheringProviderInputs.fromProcessEnvironment();
    UserApiContractHarness? accountHarness;
    _GatheringProviderHarness? gatheringHarness;
    final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

    try {
      accountHarness = await UserApiContractHarness.create();
      final session = await accountHarness.loginDisposableAccount(
        'gathering-watch-$suffix',
      );
      final personaId = session.activePersona?.personaId.trim() ?? '';
      if (personaId.isEmpty) {
        throw StateError('availability watch actor requires an active persona');
      }
      gatheringHarness = await _GatheringProviderHarness.create(
        session: session,
        personaId: personaId,
      );

      final before = await gatheringHarness.remote.getDetail(
        GatheringDetailQuery(gatheringId: inputs.gatheringId),
      );
      final publicBefore = _requireWatchableGathering(
        before,
        inputs.gatheringId,
      );
      final intent = GatheringAvailabilityWatchCommandInput(
        idempotencyKey: 'gathering-watch-$suffix',
        gatheringId: inputs.gatheringId,
        expectedGatheringVersion: publicBefore.aggregateVersion,
        expectedWatchVersion: 0,
      );

      final first = await gatheringHarness.remote.watchAvailability(intent);
      final replay = await gatheringHarness.remote.watchAvailability(intent);
      _validateWatchReceipt(
        first,
        gatheringId: inputs.gatheringId,
        previousVersion: publicBefore.aggregateVersion,
        replayed: false,
      );
      _validateWatchReceipt(
        replay,
        gatheringId: inputs.gatheringId,
        previousVersion: publicBefore.aggregateVersion,
        replayed: true,
      );
      if (replay.aggregateVersion != first.aggregateVersion) {
        throw StateError('availability watch replay advanced the aggregate');
      }

      final after = await gatheringHarness.remote.getDetail(
        GatheringDetailQuery(gatheringId: inputs.gatheringId),
      );
      final publicAfter = _requireWatchableGathering(after, inputs.gatheringId);
      if (publicAfter.aggregateVersion != first.aggregateVersion ||
          publicAfter.capacity.maxParticipants !=
              publicBefore.capacity.maxParticipants ||
          publicAfter.capacity.occupiedSeats !=
              publicBefore.capacity.occupiedSeats ||
          publicAfter.capacity.remainingSeats !=
              publicBefore.capacity.remainingSeats ||
          publicAfter.admissionState != publicBefore.admissionState ||
          publicAfter.viewerParticipation != null) {
        throw StateError(
          'availability watch changed admission, capacity, or Participation',
        );
      }

      final events = await gatheringHarness.telemetry.waitForEvents(
        minimumCount: 6,
      );
      final publicReads = events.where(
        (event) =>
            event.canonicalOperationId ==
            cloud.AppCloudOperationIds.circleGatheringGetPublicGathering,
      );
      final watchWrites = events.where(
        (event) =>
            event.canonicalOperationId ==
            cloud
                .AppCloudOperationIds
                .circleGatheringWatchGatheringAvailability,
      );
      if (publicReads.length != 2 ||
          publicReads.any((event) => !event.succeeded) ||
          watchWrites.length != 2 ||
          watchWrites.any((event) => !event.succeeded)) {
        throw StateError(
          'availability watch did not emit the canonical production operation set',
        );
      }
    } finally {
      try {
        if (accountHarness != null) {
          await accountHarness.accountLifecycle.closeAccount(
            cloud.CloseAccountCommand(
              clientRequestId: 'gathering-watch-cleanup-$suffix',
            ),
          );
        }
      } finally {
        try {
          await gatheringHarness?.close();
        } finally {
          await accountHarness?.close();
        }
      }
    }
  });
}

GatheringPublicDetailSlice _requireWatchableGathering(
  GatheringDetailPresentationSlice? detail,
  String gatheringId,
) {
  final public = detail?.publicDetail;
  if (public == null ||
      public.gatheringId != gatheringId ||
      public.lifecycleStatus != GatheringLifecycleStatus.published ||
      public.temporalPhase != GatheringTemporalPhase.upcoming ||
      !public.capacity.full ||
      public.admissionState != GatheringAdmissionState.full ||
      public.viewerParticipation != null ||
      public.primaryAction != GatheringPrimaryAction.watchAvailability) {
    throw StateError('managed Gathering is not an upcoming watchable target');
  }
  return public;
}

void _validateWatchReceipt(
  GatheringCommandResult result, {
  required String gatheringId,
  required int previousVersion,
  required bool replayed,
}) {
  if (result.gatheringId != gatheringId ||
      result.aggregateVersion <= previousVersion ||
      result.lifecycleStatus != GatheringLifecycleStatus.published ||
      result.participationState != null ||
      result.participationVersion != null ||
      result.idempotentReplay != replayed) {
    throw StateError('availability watch receipt is not canonical');
  }
}

final class _GatheringProviderInputs {
  const _GatheringProviderInputs({required this.gatheringId});

  final String gatheringId;

  static _GatheringProviderInputs fromProcessEnvironment() {
    final gatheringId =
        Platform.environment['QWQ_GATHERING_PROVIDER_GATHERING_ID']?.trim() ??
        '';
    final acknowledged =
        Platform.environment['QWQ_GATHERING_PROVIDER_TARGET_ACK']?.trim() ==
        'true';
    if (gatheringId.isEmpty || !acknowledged) {
      throw StateError('managed Gathering Provider target is not configured');
    }
    return _GatheringProviderInputs(gatheringId: gatheringId);
  }
}

final class _GatheringProviderHarness {
  const _GatheringProviderHarness({
    required this.remote,
    required this.telemetry,
    required this._httpClient,
  });

  final RemoteGatheringFacet remote;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final CloudHttpClient _httpClient;

  static Future<_GatheringProviderHarness> create({
    required cloud.AuthSessionGrant session,
    required String personaId,
  }) async {
    if (_apiContractEnv != 'gamma') {
      throw StateError('Gathering Provider runner requires gamma');
    }
    final gateway = Uri.tryParse(_apiBase);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.scheme != 'https' ||
        gateway.host.isEmpty ||
        gateway.userInfo.isNotEmpty ||
        gateway.hasFragment) {
      throw StateError('Gathering Provider runner requires an HTTPS gateway');
    }
    const clientContext = _GatheringClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final httpClient = CloudHttpClient(
      authTokenProvider: _FixedTokenProvider(session.accessToken),
    );
    try {
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: gateway,
        ),
      );
      cloud.CloudOperationInvocationContext invocationContext(
        String clientPageId, {
        String? idempotencyKey,
      }) => cloud.CloudOperationInvocationContext(
        surfaceId: AppUiSurfaces.gatheringDetail.id,
        routeId: AppUiSurfaces.gatheringDetail.routeId,
        clientPageId: clientPageId,
        idempotencyKey: idempotencyKey,
        actor: cloud.CloudOperationActorContext(
          accountId: session.ownerId,
          personaId: personaId,
          deviceActorId: 'gathering-provider-api-runner',
        ),
      );
      return _GatheringProviderHarness(
        remote: RemoteGatheringFacet(
          client: client,
          invocationContext: invocationContext,
          planReader: GatheringBoardPlanReaderFacade(
            RemoteGatheringPlanFacet(
              client: client,
              invocationContext: invocationContext,
            ),
          ),
        ),
        telemetry: telemetry,
        httpClient: httpClient,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  Future<void> close() async {
    _httpClient.close();
    await telemetry.dispose();
  }
}

final class _FixedTokenProvider implements CloudAuthTokenProvider {
  const _FixedTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class _GatheringClientContext implements CloudClientContextProvider {
  const _GatheringClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gathering-provider-api-runner',
      deviceActorId: 'gathering-provider-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
