// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/spec.md#sit-008
/// 「我的行动」ByHost 公开读面的 production Remote 合同 runner（gamma）。
///
/// 用一次性账号的 persona host 身份 readback 自己的公开行动页：新账号无公开
/// 行动，typed page 必须解码成功且诚实为空（items 空、hasMore=false）——
/// 这证明 REQ-008 的读链（generated client → RemoteGatheringFacet.listByHost）
/// 在真实环境可用且不伪造数据；若受管 host 配置存在则进一步断言非空分组事实。
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
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';
import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

void main() {
  test(
    'production Remote lists host public gatherings as a typed honest page',
    () async {
      UserApiContractHarness? accountHarness;
      _ByHostHarness? hostHarness;
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

      try {
        accountHarness = await UserApiContractHarness.create();
        final session = await accountHarness.loginDisposableAccount(
          'gathering-by-host-$suffix',
        );
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('by-host readback requires an active persona');
        }
        hostHarness = await _ByHostHarness.create(
          session: session,
          personaId: personaId,
        );

        // 新建 persona host 的公开行动页必须诚实为空（不伪造行动供给）。
        final page = await hostHarness.remote.listByHost(
          GatheringByHostListQuery(
            hostSubjectKind: 'persona',
            hostSubjectId: personaId,
          ),
        );
        if (page.items.isNotEmpty || page.hasMore) {
          throw StateError(
            'fresh persona host returned non-empty public gathering page',
          );
        }

        // host 本人私有读面（ListMyHostedGatherings）同样诚实为空：身份由
        // 服务端从受信 persona 解析，新账号无 draft 与非公开行动。
        final minePage = await hostHarness.remote.listMine(
          const GatheringMineListQuery(),
        );
        if (minePage.items.isNotEmpty || minePage.hasMore) {
          throw StateError(
            'fresh persona returned non-empty private hosted gathering page',
          );
        }

        // 受管 host（可选注入）：验证非空 typed page 的分组事实字段齐备。
        final managedHostId =
            Platform.environment['QWQ_GATHERING_MANAGED_HOST_PERSONA_ID']
                ?.trim() ??
            '';
        if (managedHostId.isNotEmpty) {
          final managedPage = await hostHarness.remote.listByHost(
            GatheringByHostListQuery(
              hostSubjectKind: 'persona',
              hostSubjectId: managedHostId,
            ),
          );
          if (managedPage.items.isEmpty) {
            throw StateError('managed host returned no public gatherings');
          }
          for (final card in managedPage.items) {
            if (card.gatheringId.trim().isEmpty ||
                card.lifecycleStatusWire.trim().isEmpty ||
                card.temporalPhaseWire.trim().isEmpty) {
              throw StateError('by-host card misses grouping facts');
            }
          }
        }

        final events = await hostHarness.telemetry.waitForEvents(
          minimumCount: 2,
        );
        final byHostReads = events.where(
          (event) =>
              event.canonicalOperationId ==
              cloud.AppCloudOperationIds.circleGatheringListGatheringsByHost,
        );
        final mineReads = events.where(
          (event) =>
              event.canonicalOperationId ==
              cloud.AppCloudOperationIds.circleGatheringListMyHostedGatherings,
        );
        if (byHostReads.isEmpty ||
            byHostReads.any((event) => !event.succeeded) ||
            mineReads.isEmpty ||
            mineReads.any((event) => !event.succeeded)) {
          throw StateError(
            'host readbacks did not emit the canonical production operations',
          );
        }
      } finally {
        try {
          if (accountHarness != null) {
            await accountHarness.accountLifecycle.closeAccount(
              cloud.CloseAccountCommand(
                clientRequestId: 'gathering-by-host-cleanup-$suffix',
              ),
            );
          }
        } finally {
          try {
            await hostHarness?.close();
          } finally {
            await accountHarness?.close();
          }
        }
      }
    },
  );
}

final class _ByHostHarness {
  const _ByHostHarness({
    required this.remote,
    required this.telemetry,
    required this._httpClient,
  });

  final RemoteGatheringFacet remote;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final CloudHttpClient _httpClient;

  static Future<_ByHostHarness> create({
    required cloud.AuthSessionGrant session,
    required String personaId,
  }) async {
    if (_apiContractEnv != 'gamma') {
      throw StateError('by-host readback runner requires gamma');
    }
    final gateway = Uri.tryParse(_apiBase);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.scheme != 'https' ||
        gateway.host.isEmpty ||
        gateway.userInfo.isNotEmpty ||
        gateway.hasFragment) {
      throw StateError('by-host readback runner requires an HTTPS gateway');
    }
    const clientContext = _ByHostClientContext();
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
        surfaceId: AppUiSurfaces.myGatherings.id,
        routeId: AppUiSurfaces.myGatherings.routeId,
        clientPageId: clientPageId,
        idempotencyKey: idempotencyKey,
        actor: cloud.CloudOperationActorContext(
          accountId: session.ownerId,
          personaId: personaId,
          deviceActorId: 'gathering-by-host-api-runner',
        ),
      );
      return _ByHostHarness(
        remote: RemoteGatheringFacet(
          client: client,
          invocationContext: invocationContext,
          planReader: RemoteGatheringPlanFacet(
            client: client,
            invocationContext: invocationContext,
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

final class _ByHostClientContext implements CloudClientContextProvider {
  const _ByHostClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gathering-by-host-api-runner',
      deviceActorId: 'gathering-by-host-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
