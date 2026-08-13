import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/notification_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification/application/notification_facets.dart';
import 'package:quwoquan_app/service/notification_service/notification_delivery/notification_delivery_job/application/public/incoming_call_presentation_acknowledger.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'api_contract_environment.dart';
import 'production_cloud_operation_telemetry_evidence.dart';

const notificationApiContractDeviceId = 'notification-api-contract-device';

final class NotificationApiContractHarness {
  NotificationApiContractHarness._({
    required this._httpClient,
    required this._tokenProvider,
    required this.telemetry,
    required this.query,
    required this.commandWriter,
    required this.session,
  });

  static Future<NotificationApiContractHarness> create() async {
    final environment = ApiContractEnvironment.resolve();
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _NotificationApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: environment,
    );

    try {
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: notificationApiContractDeviceId,
          ),
        ),
      );
      final session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'notification-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'notification-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      late NotificationApiContractHarness harness;
      CloudOperationInvocationContext invocationContext(String clientPageId) =>
          harness._invocationContext(clientPageId);
      final facets = NotificationProductionComposition.appMessageFacets(
        client: client,
        invocationContext: invocationContext,
      );

      harness = NotificationApiContractHarness._(
        httpClient: httpClient,
        tokenProvider: tokenProvider,
        telemetry: telemetry,
        query: facets.query,
        commandWriter: facets.commandWriter,
        session: session,
      );
      return harness;
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final _MutableAccessTokenProvider _tokenProvider;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final AppMessageQuery query;
  final AppMessageCommandWriter commandWriter;
  AuthSessionGrant session;

  Future<T> withSession<T>({
    required AuthSessionGrant session,
    required Future<T> Function() action,
  }) async {
    final currentSession = this.session;
    final currentAccessToken = _tokenProvider.accessToken;
    this.session = session;
    _tokenProvider.accessToken = session.accessToken;
    try {
      return await action();
    } finally {
      this.session = currentSession;
      _tokenProvider.accessToken = currentAccessToken;
    }
  }

  Future<void> close() async {
    try {
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }

  CloudOperationInvocationContext _invocationContext(String clientPageId) {
    return CloudOperationInvocationContext(
      surfaceId: AppUiSurfaces.chatList.id,
      routeId: AppUiSurfaces.chatList.routeId,
      clientPageId: clientPageId,
      actor: CloudOperationActorContext(
        accountId: session.ownerId,
        personaId: session.activePersona?.personaId,
        deviceActorId: notificationApiContractDeviceId,
      ),
    );
  }
}

const _incomingCallAccessToken = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_ACCESS_TOKEN',
);
const _incomingCallOwnerId = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_OWNER_ID',
);
const _incomingCallPersonaId = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_PERSONA_ID',
);
const _incomingCallDeviceId = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_DEVICE_ID',
);
const _incomingCallId = String.fromEnvironment('API_CONTRACT_INCOMING_CALL_ID');
const _incomingCallDeliveryKey = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_DELIVERY_KEY',
);
const _incomingCallSource = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_PRESENTATION_SOURCE',
);
const _incomingCallPresentedAt = String.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_PRESENTED_AT',
);
const _incomingCallReceiptAcknowledged = bool.fromEnvironment(
  'API_CONTRACT_INCOMING_CALL_RECEIPT_ACKNOWLEDGED',
);

final class NotificationIncomingCallApiContractHarness {
  NotificationIncomingCallApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.writer,
    required this.receipt,
  });

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final NotificationDeliveryJobProcessCommandWriter writer;
  final IncomingCallPresentationReceipt receipt;

  static Future<NotificationIncomingCallApiContractHarness> create() async {
    final inputs = _IncomingCallApiContractInputs.resolve();
    final environment = ApiContractEnvironment.resolve();
    final clientContext = _IncomingCallApiClientContext(inputs.deviceId);
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final httpClient = CloudHttpClient(
      authTokenProvider: _FixedAccessTokenProvider(inputs.accessToken),
    );
    try {
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: environment,
      );
      final writer =
          NotificationProductionComposition.generatedAdapter<
            NotificationDeliveryJobProcessCommandWriter
          >(
            NotificationProductionAdapter.incomingCallPresentation,
            client: client,
            invocationContext: (String clientPageId) =>
                CloudOperationInvocationContext(
                  surfaceId: AppUiSurfaces.rtcIncoming.id,
                  routeId: AppUiSurfaces.rtcIncoming.routeId,
                  clientPageId: clientPageId,
                  actor: CloudOperationActorContext(
                    accountId: inputs.ownerId,
                    personaId: inputs.personaId,
                    deviceActorId: inputs.deviceId,
                  ),
                ),
          );
      return NotificationIncomingCallApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        writer: writer,
        receipt: inputs.receipt,
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

final class _IncomingCallApiContractInputs {
  const _IncomingCallApiContractInputs({
    required this.accessToken,
    required this.ownerId,
    required this.personaId,
    required this.deviceId,
    required this.receipt,
  });

  final String accessToken;
  final String ownerId;
  final String personaId;
  final String deviceId;
  final IncomingCallPresentationReceipt receipt;

  static _IncomingCallApiContractInputs resolve() {
    final values = <String, String>{
      'access token': _incomingCallAccessToken.trim(),
      'owner id': _incomingCallOwnerId.trim(),
      'persona id': _incomingCallPersonaId.trim(),
      'device id': _incomingCallDeviceId.trim(),
      'call id': _incomingCallId.trim(),
      'delivery key': _incomingCallDeliveryKey.trim(),
    };
    final missing = values.entries
        .where((entry) => entry.value.isEmpty)
        .map((entry) => entry.key)
        .toList(growable: false);
    final source = switch (_incomingCallSource.trim()) {
      'realtime' => IncomingCallPresentationSource.realtime,
      'native_push' => IncomingCallPresentationSource.nativePush,
      _ => null,
    };
    final presentedAt = DateTime.tryParse(
      _incomingCallPresentedAt.trim(),
    )?.toUtc();
    if (!_incomingCallReceiptAcknowledged ||
        missing.isNotEmpty ||
        source == null ||
        presentedAt == null) {
      throw StateError(
        'managed incoming-call presentation receipt is not configured: '
        '${missing.join(', ')}',
      );
    }
    final now = DateTime.now().toUtc();
    if (presentedAt.isBefore(now.subtract(const Duration(minutes: 2))) ||
        presentedAt.isAfter(now.add(const Duration(seconds: 15)))) {
      throw StateError(
        'managed incoming-call presentation receipt is stale or future-dated',
      );
    }
    return _IncomingCallApiContractInputs(
      accessToken: values['access token']!,
      ownerId: values['owner id']!,
      personaId: values['persona id']!,
      deviceId: values['device id']!,
      receipt: IncomingCallPresentationReceipt(
        callId: values['call id']!,
        deliveryKey: values['delivery key']!,
        source: source,
        presentedAt: presentedAt,
      ),
    );
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _FixedAccessTokenProvider implements CloudAuthTokenProvider {
  const _FixedAccessTokenProvider(this._accessToken);

  final String _accessToken;

  @override
  Future<String?> getAccessToken() async => _accessToken;
}

final class _NotificationApiClientContext
    implements CloudClientContextProvider {
  const _NotificationApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'notification-api-contract',
      deviceActorId: notificationApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

final class _IncomingCallApiClientContext
    implements CloudClientContextProvider {
  const _IncomingCallApiClientContext(this._deviceActorId);

  final String _deviceActorId;

  @override
  CloudClientContextSnapshot snapshot() {
    return CloudClientContextSnapshot(
      sessionId: 'incoming-call-provider-api-runner',
      deviceActorId: _deviceActorId,
      platform: 'ios',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
