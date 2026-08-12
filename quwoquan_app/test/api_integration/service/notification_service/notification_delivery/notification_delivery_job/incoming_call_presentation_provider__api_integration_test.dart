// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
/// 受管来电 Provider 展示 receipt 的 production Remote ACK runner。
///
/// access token、deliveryKey 与设备身份只允许由进程环境注入，禁止进入
/// dart-define、日志和断言。当前不登记 readiness_case：该 source runner 只消费同一
/// 次真实物理展示产生的短时 receipt；完整 realtime/push/CallKit、timeline readback 与
/// Android+iPhone ResultBundle 由环境 UAT 独立验收。
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/adapters/incoming_call_presentation_remote.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as cloud;

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

void main() {
  test(
    'production Remote acknowledges one fresh physical incoming-call presentation receipt',
    () async {
      final inputs = _IncomingCallProviderInputs.fromProcessEnvironment();
      final gateway = _requireGammaGateway();
      const clientContext = _IncomingCallAckClientContext();
      final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
        clientContextProvider: clientContext,
      );
      final httpClient = CloudHttpClient(
        authTokenProvider: _FixedTokenProvider(inputs.accessToken),
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
        final writer = RemoteIncomingCallPresentationAcknowledger(
          client: client,
          invocationContext: (clientPageId) =>
              cloud.CloudOperationInvocationContext(
                surfaceId: AppUiSurfaces.rtcIncoming.id,
                routeId: AppUiSurfaces.rtcIncoming.routeId,
                clientPageId: clientPageId,
                actor: cloud.CloudOperationActorContext(
                  accountId: inputs.ownerId,
                  personaId: inputs.personaId,
                  deviceActorId: inputs.deviceId,
                ),
              ),
        );

        await writer.acknowledge(
          IncomingCallPresentationReceipt(
            callId: inputs.callId,
            deliveryKey: inputs.deliveryKey,
            source: inputs.source,
            presentedAt: inputs.presentedAt,
          ),
        );

        final events = await telemetry.waitForEvents(minimumCount: 1);
        if (events.length != 1 ||
            !events.single.succeeded ||
            events.single.canonicalOperationId !=
                cloud
                    .AppCloudOperationIds
                    .notificationNotificationDeliveryJobAckIncomingCallPresentation) {
          throw StateError(
            'incoming-call presentation did not emit one canonical successful ACK',
          );
        }
      } finally {
        httpClient.close();
        await telemetry.dispose();
      }
    },
  );
}

Uri _requireGammaGateway() {
  if (_apiContractEnv != 'gamma') {
    throw StateError('incoming-call Provider runner requires gamma');
  }
  final gateway = Uri.tryParse(_apiBase);
  if (gateway == null ||
      !gateway.isAbsolute ||
      gateway.scheme != 'https' ||
      gateway.host.isEmpty ||
      gateway.userInfo.isNotEmpty ||
      gateway.hasFragment) {
    throw StateError('incoming-call Provider runner requires an HTTPS gateway');
  }
  return gateway;
}

final class _IncomingCallProviderInputs {
  const _IncomingCallProviderInputs({
    required this.accessToken,
    required this.ownerId,
    required this.personaId,
    required this.deviceId,
    required this.callId,
    required this.deliveryKey,
    required this.source,
    required this.presentedAt,
  });

  final String accessToken;
  final String ownerId;
  final String personaId;
  final String deviceId;
  final String callId;
  final String deliveryKey;
  final IncomingCallPresentationSource source;
  final DateTime presentedAt;

  static _IncomingCallProviderInputs fromProcessEnvironment() {
    final environment = Platform.environment;
    final accessToken =
        environment['QWQ_INCOMING_CALL_ACK_ACCESS_TOKEN']?.trim() ?? '';
    final ownerId = environment['QWQ_INCOMING_CALL_ACK_OWNER_ID']?.trim() ?? '';
    final personaId =
        environment['QWQ_INCOMING_CALL_ACK_PERSONA_ID']?.trim() ?? '';
    final deviceId =
        environment['QWQ_INCOMING_CALL_ACK_DEVICE_ID']?.trim() ?? '';
    final callId = environment['QWQ_INCOMING_CALL_ID']?.trim() ?? '';
    final deliveryKey =
        environment['QWQ_INCOMING_CALL_DELIVERY_KEY']?.trim() ?? '';
    final source = switch (environment['QWQ_INCOMING_CALL_PRESENTATION_SOURCE']
        ?.trim()) {
      'realtime' => IncomingCallPresentationSource.realtime,
      'native_push' => IncomingCallPresentationSource.nativePush,
      _ => null,
    };
    final presentedAt = DateTime.tryParse(
      environment['QWQ_INCOMING_CALL_PRESENTED_AT']?.trim() ?? '',
    )?.toUtc();
    final acknowledged =
        environment['QWQ_INCOMING_CALL_PROVIDER_RECEIPT_ACK']?.trim() == 'true';
    if (!acknowledged ||
        accessToken.isEmpty ||
        ownerId.isEmpty ||
        personaId.isEmpty ||
        deviceId.isEmpty ||
        callId.isEmpty ||
        deliveryKey.isEmpty ||
        source == null ||
        presentedAt == null) {
      throw StateError(
        'managed incoming-call presentation receipt is not configured',
      );
    }
    final now = DateTime.now().toUtc();
    if (presentedAt.isBefore(now.subtract(const Duration(minutes: 2))) ||
        presentedAt.isAfter(now.add(const Duration(seconds: 15)))) {
      throw StateError(
        'managed incoming-call presentation receipt is stale or future-dated',
      );
    }
    return _IncomingCallProviderInputs(
      accessToken: accessToken,
      ownerId: ownerId,
      personaId: personaId,
      deviceId: deviceId,
      callId: callId,
      deliveryKey: deliveryKey,
      source: source,
      presentedAt: presentedAt,
    );
  }
}

final class _FixedTokenProvider implements CloudAuthTokenProvider {
  const _FixedTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class _IncomingCallAckClientContext
    implements CloudClientContextProvider {
  const _IncomingCallAckClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'incoming-call-provider-api-runner',
      deviceActorId: 'incoming-call-provider-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
