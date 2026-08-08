import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/integration/integration_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_connection/adapters/connector_management_remote.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_definition/adapters/connector_definition_remote.dart';
import 'package:quwoquan_app/service/integration_service/external_integration/connector_invocation/adapters/connector_invocation_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const integrationApiContractDeviceId = 'integration-api-contract-device';

/// Production App composition for Connector read-side API contracts.
///
/// The harness creates a short-lived account only through the public anonymous
/// login operation and removes it through the canonical account command. It
/// never creates Connector state, injects a grant receipt, or substitutes the
/// gateway/process/storage boundary.
final class IntegrationApiContractHarness {
  IntegrationApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.definitions,
    required this.connections,
    required this.invocations,
    required this._accountLifecycle,
    required this._ownedSession,
  });

  static Future<IntegrationApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: API_CONTRACT_BASE_URL not set');
    }

    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _IntegrationApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );

    try {
      AuthSessionGrant? session;
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.values.firstWhere(
            (candidate) => candidate.name == _apiContractEnv,
            orElse: () => throw StateError(
              'Unsupported API_CONTRACT_ENV: $_apiContractEnv',
            ),
          ),
          gatewayBaseUri: Uri.parse(_apiBase),
        ),
      );

      CloudOperationInvocationContext invocationContext(
        String clientPageId, {
        String? idempotencyKey,
      }) {
        final surface = _surfaceForClientPage(clientPageId);
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: clientPageId == UserRequestPageIds.closeAccount
              ? 'integration-api-account-cleanup-${session?.ownerId}'
              : idempotencyKey,
          actor: CloudOperationActorContext(
            accountId: session?.ownerId,
            personaId: session?.activePersona?.personaId,
            deviceActorId: integrationApiContractDeviceId,
          ),
        );
      }

      CloudOperationInvocationContext readInvocationContext(
        String clientPageId,
      ) => invocationContext(clientPageId);

      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: readInvocationContext,
      );
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'integration-api-contract-$suffix',
          deviceFingerprintHash: 'integration-api-contract-$suffix',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

      return IntegrationApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        definitions: RemoteConnectorDefinitionReader(
          client: client,
          invocationContext: readInvocationContext,
        ),
        connections: RemoteConnectorManagementFacet(
          client: client,
          invocationContext: invocationContext,
          definitionReader: RemoteConnectorDefinitionReader(
            client: client,
            invocationContext: readInvocationContext,
          ),
          invocationReader: RemoteConnectorInvocationReader(
            client: client,
            invocationContext: readInvocationContext,
          ),
        ),
        invocations: RemoteConnectorInvocationReader(
          client: client,
          invocationContext: readInvocationContext,
        ),
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: readInvocationContext,
        ),
        ownedSession: session,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  /// Creates a production Remote composition for the candidate-bound
  /// Connector account that owns [inputs.grantReceiptRef].
  ///
  /// Unlike [create], this factory never creates or closes an account. The
  /// caller must revoke every connection it creates before disposing the
  /// harness. The access token and one-time grant receipt are read only from
  /// the process environment and are never emitted to logs or evidence.
  static Future<IntegrationApiContractHarness> createForConnectorConnection(
    ConnectorConnectionApiInputs inputs,
  ) async {
    if (_apiContractEnv != 'gamma') {
      throw StateError(
        'Connector Connection API contract requires API_CONTRACT_ENV=gamma',
      );
    }
    if (_apiBase.isEmpty) {
      throw StateError(
        'Connector Connection API contract requires API_CONTRACT_BASE_URL',
      );
    }

    final tokenProvider = _MutableAccessTokenProvider()
      ..accessToken = inputs._accessToken;
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _IntegrationApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );

    try {
      final client = buildGeneratedCloudOperationClient(
        httpClient: httpClient,
        clientContextProvider: clientContext,
        telemetrySink: telemetry.sink,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_apiBase),
        ),
      );

      CloudOperationInvocationContext invocationContext(
        String clientPageId, {
        String? idempotencyKey,
      }) {
        final surface = _surfaceForClientPage(clientPageId);
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          idempotencyKey: idempotencyKey,
          actor: CloudOperationActorContext(
            accountId: inputs.accountId,
            personaId: inputs.personaId,
            deviceActorId: integrationApiContractDeviceId,
          ),
        );
      }

      CloudOperationInvocationContext readInvocationContext(
        String clientPageId,
      ) => invocationContext(clientPageId);

      final definitions = RemoteConnectorDefinitionReader(
        client: client,
        invocationContext: readInvocationContext,
      );
      final invocations = RemoteConnectorInvocationReader(
        client: client,
        invocationContext: readInvocationContext,
      );
      return IntegrationApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        definitions: definitions,
        connections: RemoteConnectorManagementFacet(
          client: client,
          invocationContext: invocationContext,
          definitionReader: definitions,
          invocationReader: invocations,
        ),
        invocations: invocations,
        accountLifecycle: null,
        ownedSession: null,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final RemoteAccountLifecycleCommandWriter? _accountLifecycle;
  final AuthSessionGrant? _ownedSession;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final RemoteConnectorDefinitionReader definitions;
  final RemoteConnectorManagementFacet connections;
  final RemoteConnectorInvocationReader invocations;

  Future<void> close() async {
    try {
      final accountLifecycle = _accountLifecycle;
      final ownedSession = _ownedSession;
      if (accountLifecycle != null && ownedSession != null) {
        await accountLifecycle.closeAccount(
          CloseAccountCommand(
            clientRequestId: 'integration-api-cleanup-${ownedSession.ownerId}',
          ),
        );
      }
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

AppUiSurface _surfaceForClientPage(String clientPageId) {
  if (clientPageId == UserRequestPageIds.loginAnonymous) {
    return AppUiSurfaces.appShell;
  }
  if (clientPageId == UserRequestPageIds.closeAccount) {
    return AppUiSurfaces.settingsAccountSecurity;
  }
  if (clientPageId == IntegrationRequestPageIds.listConnectorDefinitions ||
      clientPageId == IntegrationRequestPageIds.getConnectorDefinition ||
      clientPageId == IntegrationRequestPageIds.listConnectorConnections ||
      clientPageId == IntegrationRequestPageIds.getConnectorConnection ||
      clientPageId == IntegrationRequestPageIds.createConnectorConnection ||
      clientPageId == IntegrationRequestPageIds.revokeConnectorConnection ||
      clientPageId == IntegrationRequestPageIds.listConnectorInvocations ||
      clientPageId == IntegrationRequestPageIds.getConnectorInvocation) {
    return AppUiSurfaces.assistantSkills;
  }
  throw StateError(
    'unsupported Integration API contract clientPageId: $clientPageId',
  );
}

/// Candidate-bound, runtime-only inputs for a Connector Connection API run.
///
/// The bearer and one-time receipt stay process-local. Error messages only
/// name missing variables and never interpolate their values.
final class ConnectorConnectionApiInputs {
  ConnectorConnectionApiInputs._({
    required this._accessToken,
    required this.accountId,
    required this.personaId,
    required this.connectorId,
    required this.requestedCapability,
    required this.grantReceiptRef,
  });

  final String _accessToken;
  final String accountId;
  final String? personaId;
  final String connectorId;
  final String requestedCapability;
  final String grantReceiptRef;

  List<String> get requestedCapabilities => <String>[requestedCapability];

  static ConnectorConnectionApiInputs fromEnvironment() {
    final environment = Platform.environment;
    final accessToken = _requiredEnvironmentValue(
      environment,
      'TEST_AUTH_TOKEN',
    );
    final accountId = _requiredEnvironmentValue(environment, 'TEST_ACCOUNT_ID');
    final connectorId = _requiredEnvironmentValue(
      environment,
      'INTEGRATION_CONNECTOR_ID',
    );
    final capability = _requiredEnvironmentValue(
      environment,
      'INTEGRATION_CONNECTOR_CAPABILITY',
    );
    final grantReceiptRef = _requiredEnvironmentValue(
      environment,
      'INTEGRATION_CONNECTOR_GRANT_RECEIPT_REF',
    );
    final personaId = environment['TEST_PERSONA_ID']?.trim();
    return ConnectorConnectionApiInputs._(
      accessToken: accessToken,
      accountId: accountId,
      personaId: personaId == null || personaId.isEmpty ? null : personaId,
      connectorId: connectorId,
      requestedCapability: capability,
      grantReceiptRef: grantReceiptRef,
    );
  }

  String createIdempotencyKey() => _idempotencyKey('create', <String>[
    connectorId,
    requestedCapability,
    grantReceiptRef,
  ]);

  String revokeIdempotencyKey(ConnectorConnectionView connection) =>
      _idempotencyKey('revoke', <String>[
        connection.connectionId,
        connection.revision.toString(),
      ]);

  static String _idempotencyKey(String action, List<String> identity) {
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch;
    final digest = sha256
        .convert(
          utf8.encode(identity.map((value) => value.trim()).join('\u0000')),
        )
        .toString();
    return 'connector-$action-${digest.substring(0, 24)}-$nonce';
  }
}

String _requiredEnvironmentValue(Map<String, String> environment, String name) {
  final value = environment[name]?.trim() ?? '';
  if (value.isEmpty) {
    throw StateError('Connector Connection API contract requires $name');
  }
  return value;
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _IntegrationApiClientContext implements CloudClientContextProvider {
  const _IntegrationApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'integration-api-contract',
      deviceActorId: integrationApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
