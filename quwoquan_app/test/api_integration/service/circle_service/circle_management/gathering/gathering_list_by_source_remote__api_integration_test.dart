// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007.t3
// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/entity-homepage-intersection-redesign/spec.md#gwt-001
/// 「近期行动」BySource 公开读面的 production Remote 合同 runner（gamma）。
///
/// 用一次性账号对「形状合法但必然无匹配」的 canonical source identity 执行
/// readback：typed page 必须解码成功且诚实为空（items 空、hasMore=false）——
/// 证明实体页「近期行动」区块的读链（generated client →
/// RemoteGatheringFacet.listBySource）在真实环境可用且不伪造数据、不回退模糊
/// 匹配；若受管 release 实体注入存在则进一步断言非空 typed 卡片事实。
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
    'production Remote lists source public gatherings as a typed honest page',
    () async {
      UserApiContractHarness? accountHarness;
      _BySourceHarness? sourceHarness;
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();

      try {
        accountHarness = await UserApiContractHarness.create();
        final session = await accountHarness.loginDisposableAccount(
          'gathering-by-source-$suffix',
        );
        final personaId = session.activePersona?.personaId.trim() ?? '';
        if (personaId.isEmpty) {
          throw StateError('by-source readback requires an active persona');
        }
        sourceHarness = await _BySourceHarness.create(
          session: session,
          personaId: personaId,
        );

        // 形状合法但必然无匹配的一次性 source identity：typed empty page，
        // 不合成失败也不借用其他来源结果（GWT-007.t3）。
        final page = await sourceHarness.remote.listBySource(
          GatheringBySourceListQuery(
            sourceObjectTypeRef: 'homepage',
            sourceObjectId: 'homepage-by-source-runner-$suffix',
          ),
        );
        if (page.isNotEmpty) {
          throw StateError(
            'unmatched source identity returned non-empty public gathering page',
          );
        }

        // 受管 release 实体（可选注入）：验证非空 typed 卡片的公开事实字段齐备。
        final managedHomepageId =
            Platform.environment['QWQ_GATHERING_SOURCE_HOMEPAGE_ID']?.trim() ??
            '';
        if (managedHomepageId.isNotEmpty) {
          final managedPage = await sourceHarness.remote.listBySource(
            GatheringBySourceListQuery(
              sourceObjectTypeRef: 'homepage',
              sourceObjectId: managedHomepageId,
            ),
          );
          if (managedPage.isEmpty) {
            throw StateError('managed source returned no public gatherings');
          }
          for (final card in managedPage) {
            if (card.gatheringId.trim().isEmpty ||
                card.title.trim().isEmpty ||
                card.lifecycleStatusWire.trim().isEmpty) {
              throw StateError('by-source card misses public facts');
            }
          }
        }

        final events = await sourceHarness.telemetry.waitForEvents(
          minimumCount: 1,
        );
        final bySourceReads = events.where(
          (event) =>
              event.canonicalOperationId ==
              cloud.AppCloudOperationIds.circleGatheringListGatheringsBySource,
        );
        if (bySourceReads.isEmpty ||
            bySourceReads.any((event) => !event.succeeded)) {
          throw StateError(
            'by-source readback did not emit the canonical production operation',
          );
        }
      } finally {
        try {
          if (accountHarness != null) {
            await accountHarness.accountLifecycle.closeAccount(
              cloud.CloseAccountCommand(
                clientRequestId: 'gathering-by-source-cleanup-$suffix',
              ),
            );
          }
        } finally {
          try {
            await sourceHarness?.close();
          } finally {
            await accountHarness?.close();
          }
        }
      }
    },
  );
}

final class _BySourceHarness {
  const _BySourceHarness({
    required this.remote,
    required this.telemetry,
    required this._httpClient,
  });

  final RemoteGatheringFacet remote;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final CloudHttpClient _httpClient;

  static Future<_BySourceHarness> create({
    required cloud.AuthSessionGrant session,
    required String personaId,
  }) async {
    if (_apiContractEnv != 'gamma') {
      throw StateError('by-source readback runner requires gamma');
    }
    final gateway = Uri.tryParse(_apiBase);
    if (gateway == null ||
        !gateway.isAbsolute ||
        gateway.scheme != 'https' ||
        gateway.host.isEmpty ||
        gateway.userInfo.isNotEmpty ||
        gateway.hasFragment) {
      throw StateError('by-source readback runner requires an HTTPS gateway');
    }
    const clientContext = _BySourceClientContext();
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
      return _BySourceHarness(
        remote: RemoteGatheringFacet(
          client: client,
          invocationContext: (clientPageId, {idempotencyKey}) =>
              cloud.CloudOperationInvocationContext(
                surfaceId: AppUiSurfaces.homepageDetail.id,
                routeId: AppUiSurfaces.homepageDetail.routeId,
                clientPageId: clientPageId,
                idempotencyKey: idempotencyKey,
                actor: cloud.CloudOperationActorContext(
                  accountId: session.ownerId,
                  personaId: personaId,
                  deviceActorId: 'gathering-by-source-api-runner',
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

final class _BySourceClientContext implements CloudClientContextProvider {
  const _BySourceClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'gathering-by-source-api-runner',
      deviceActorId: 'gathering-by-source-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
