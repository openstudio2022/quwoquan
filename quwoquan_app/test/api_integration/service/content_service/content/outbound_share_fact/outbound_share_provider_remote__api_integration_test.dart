// spec_ref: specs/feature-tree/product-ops-growth/outbound-share-distribution/share-attribution-and-token/spec.md#gwt-003
/// 受管外部分享 Provider receipt 的 production Remote OutboundShareFact runner。
///
/// access token、providerReceiptId 与归因身份只允许由进程环境注入，禁止进入
/// dart-define、日志和断言。当前不登记 readiness_case：receipt 必须由同一次真实系统/
/// 微信分享完成回调生成；五类对象、入站解析和同 candidate 双真机证据仍由环境 UAT
/// 独立验收。
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/content_service/content/outbound_share_fact/adapters/outbound_share_remote.dart';
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
    'production Remote appends and replays one fresh external-share Provider receipt',
    () async {
      final inputs = _OutboundShareProviderInputs.fromProcessEnvironment();
      final gateway = _requireGammaGateway();
      const clientContext = _OutboundShareClientContext();
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
        final writer = RemoteContentOutboundShareAppendWriter(
          client: client,
          invocationContext: (clientPageId, command) =>
              cloud.CloudOperationInvocationContext(
                surfaceId: AppUiSurfaces.workBrowser.id,
                routeId: AppUiSurfaces.workBrowser.routeId,
                clientPageId: clientPageId,
                idempotencyKey: command.referralId,
                actor: cloud.CloudOperationActorContext(
                  accountId: inputs.ownerId,
                  personaId: inputs.personaId,
                  deviceActorId: inputs.deviceId,
                ),
              ),
        );
        final command = cloud.CreateContentOutboundShareCommand(
          postId: inputs.postId,
          channel: inputs.channel,
          destinationKind: cloud.OutboundShareDestinationKind.externalApp,
          destination: inputs.destination,
          referralId: inputs.referralId,
          providerReceiptId: inputs.providerReceiptId,
          clientConfirmedAt: inputs.confirmedAt,
        );

        final first = await writer.appendOutboundShare(command);
        final replay = await writer.appendOutboundShare(command);
        _validateResult(first, inputs: inputs, replayed: false);
        _validateResult(replay, inputs: inputs, replayed: true);
        if (replay.eventId != first.eventId ||
            replay.occurredAt != first.occurredAt) {
          throw StateError('OutboundShareFact replay changed immutable facts');
        }

        final events = await telemetry.waitForEvents(minimumCount: 2);
        if (events.length != 2 ||
            events.any((event) => !event.succeeded) ||
            events.any(
              (event) =>
                  event.canonicalOperationId !=
                  cloud
                      .AppCloudOperationIds
                      .contentOutboundShareFactAppendOutboundShareFact,
            )) {
          throw StateError(
            'OutboundShareFact did not emit two canonical successful operations',
          );
        }
      } finally {
        httpClient.close();
        await telemetry.dispose();
      }
    },
  );
}

void _validateResult(
  cloud.OutboundShareFactResult result, {
  required _OutboundShareProviderInputs inputs,
  required bool replayed,
}) {
  if (result.eventId.trim().isEmpty ||
      result.postId != inputs.postId ||
      result.channel != inputs.channel ||
      result.referralId != inputs.referralId ||
      result.occurredAt.isBefore(inputs.confirmedAt) ||
      result.replayed != replayed) {
    throw StateError('OutboundShareFact result is not canonical');
  }
}

Uri _requireGammaGateway() {
  if (_apiContractEnv != 'gamma') {
    throw StateError('OutboundShareFact Provider runner requires gamma');
  }
  final gateway = Uri.tryParse(_apiBase);
  if (gateway == null ||
      !gateway.isAbsolute ||
      gateway.scheme != 'https' ||
      gateway.host.isEmpty ||
      gateway.userInfo.isNotEmpty ||
      gateway.hasFragment) {
    throw StateError(
      'OutboundShareFact Provider runner requires an HTTPS gateway',
    );
  }
  return gateway;
}

final class _OutboundShareProviderInputs {
  const _OutboundShareProviderInputs({
    required this.accessToken,
    required this.ownerId,
    required this.personaId,
    required this.deviceId,
    required this.postId,
    required this.channel,
    required this.destination,
    required this.referralId,
    required this.providerReceiptId,
    required this.confirmedAt,
  });

  final String accessToken;
  final String ownerId;
  final String personaId;
  final String deviceId;
  final String postId;
  final cloud.OutboundShareChannel channel;
  final String destination;
  final String referralId;
  final String providerReceiptId;
  final DateTime confirmedAt;

  static _OutboundShareProviderInputs fromProcessEnvironment() {
    final environment = Platform.environment;
    final accessToken =
        environment['QWQ_OUTBOUND_SHARE_ACCESS_TOKEN']?.trim() ?? '';
    final ownerId = environment['QWQ_OUTBOUND_SHARE_OWNER_ID']?.trim() ?? '';
    final personaId =
        environment['QWQ_OUTBOUND_SHARE_PERSONA_ID']?.trim() ?? '';
    final deviceId = environment['QWQ_OUTBOUND_SHARE_DEVICE_ID']?.trim() ?? '';
    final postId = environment['QWQ_OUTBOUND_SHARE_POST_ID']?.trim() ?? '';
    final channel = switch (environment['QWQ_OUTBOUND_SHARE_CHANNEL']?.trim()) {
      'system_share' => cloud.OutboundShareChannel.systemShare,
      'wechat_friend' => cloud.OutboundShareChannel.wechatFriend,
      'wechat_moments' => cloud.OutboundShareChannel.wechatMoments,
      _ => null,
    };
    final destination =
        environment['QWQ_OUTBOUND_SHARE_DESTINATION']?.trim() ?? '';
    final referralId =
        environment['QWQ_OUTBOUND_SHARE_REFERRAL_ID']?.trim() ?? '';
    final providerReceiptId =
        environment['QWQ_OUTBOUND_SHARE_PROVIDER_RECEIPT_ID']?.trim() ?? '';
    final confirmedAt = DateTime.tryParse(
      environment['QWQ_OUTBOUND_SHARE_CONFIRMED_AT']?.trim() ?? '',
    )?.toUtc();
    final acknowledged =
        environment['QWQ_OUTBOUND_SHARE_PROVIDER_RECEIPT_ACK']?.trim() ==
        'true';
    if (!acknowledged ||
        accessToken.isEmpty ||
        ownerId.isEmpty ||
        personaId.isEmpty ||
        deviceId.isEmpty ||
        postId.isEmpty ||
        channel == null ||
        destination.isEmpty ||
        referralId.isEmpty ||
        providerReceiptId.isEmpty ||
        confirmedAt == null) {
      throw StateError('managed outbound-share receipt is not configured');
    }
    final now = DateTime.now().toUtc();
    if (confirmedAt.isBefore(now.subtract(const Duration(minutes: 2))) ||
        confirmedAt.isAfter(now.add(const Duration(seconds: 15)))) {
      throw StateError(
        'managed outbound-share receipt is stale or future-dated',
      );
    }
    return _OutboundShareProviderInputs(
      accessToken: accessToken,
      ownerId: ownerId,
      personaId: personaId,
      deviceId: deviceId,
      postId: postId,
      channel: channel,
      destination: destination,
      referralId: referralId,
      providerReceiptId: providerReceiptId,
      confirmedAt: confirmedAt,
    );
  }
}

final class _FixedTokenProvider implements CloudAuthTokenProvider {
  const _FixedTokenProvider(this._token);

  final String _token;

  @override
  Future<String?> getAccessToken() async => _token;
}

final class _OutboundShareClientContext implements CloudClientContextProvider {
  const _OutboundShareClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'outbound-share-provider-api-runner',
      deviceActorId: 'outbound-share-provider-api-runner',
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
