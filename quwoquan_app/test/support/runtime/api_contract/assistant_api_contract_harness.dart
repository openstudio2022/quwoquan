import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/assistant_dependencies.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/generated/user/user_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/application/assistant_personalization_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_session_run_facade.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_task_view/application/assistant_task_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_catalog/application/skill_catalog_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_activity_view/application/public/skill_activity_query.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/application/skill_data_control_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_subscription/application/skill_subscription_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_user_setting/application/skill_user_setting_facet.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const assistantApiContractDeviceId = 'assistant-api-contract-device';

/// Production-only Assistant composition backed by one disposable account.
///
/// Every business call passes through the generated operation client and the
/// production Assistant Remote composition. The harness installs no fixture,
/// seed, substitute transport, pre-issued token, or preselected persona.
final class AssistantApiContractHarness {
  AssistantApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.session,
    required this.preferences,
    required this.personalization,
    required this.sessionRun,
    required this.tasks,
    required this.skillCatalog,
    required this.skillSubscriptions,
    required this.skillUserSettings,
    required this.skillConsents,
    required this.skillActivities,
    required this.skillDataControlCommands,
    required this.skillDataControlQueries,
    required this._accountLifecycle,
  });

  static Future<AssistantApiContractHarness> create(String purpose) async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final normalizedPurpose = purpose.trim();
    if (normalizedPurpose.isEmpty) {
      throw ArgumentError.value(purpose, 'purpose');
    }
    final environment = CloudEnvironment.values.firstWhere(
      (candidate) => candidate.name == _apiContractEnv,
      orElse: () =>
          throw StateError('Unsupported API_CONTRACT_ENV: $_apiContractEnv'),
    );
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _AssistantApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: clientContext,
      telemetrySink: telemetry.sink,
      environment: CloudRuntimeEnvironment(
        environment: environment,
        gatewayBaseUri: Uri.parse(_apiBase),
      ),
    );

    AuthSessionGrant? session;

    CloudOperationInvocationContext invocationContext(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    }) => CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: idempotencyKey,
      actor: CloudOperationActorContext(
        accountId: session?.ownerId,
        personaId: session?.activePersona?.personaId,
        deviceActorId: assistantApiContractDeviceId,
      ),
    );

    CloudOperationInvocationContext accountInvocationContext(
      String clientPageId,
    ) => invocationContext(
      clientPageId == UserRequestPageIds.closeAccount
          ? AppUiSurfaces.settingsAccountSecurity
          : AppUiSurfaces.appShell,
      clientPageId,
      idempotencyKey: clientPageId == UserRequestPageIds.closeAccount
          ? 'assistant-api-account-cleanup-${session?.ownerId}'
          : null,
    );

    CloudOperationInvocationContext assistantInvocationContext(
      String clientPageId, {
      String? idempotencyKey,
      bool networkSurface = false,
    }) {
      if (networkSurface) {
        throw StateError(
          'Assistant API source runners do not use a network-search surface',
        );
      }
      return invocationContext(
        _assistantSurfaceForClientPage(clientPageId),
        clientPageId,
        idempotencyKey: idempotencyKey,
      );
    }

    final accountSessions = RemoteAccountSessionCommandWriter(
      client: client,
      invocationContext: accountInvocationContext,
    );
    final accountLifecycle = RemoteAccountLifecycleCommandWriter(
      client: client,
      invocationContext: accountInvocationContext,
    );
    try {
      final suffix = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'assistant-$normalizedPurpose-$suffix',
          deviceFingerprintHash: 'assistant-$normalizedPurpose-$suffix',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;
      final personaId = session.activePersona?.personaId.trim() ?? '';
      if (personaId.isEmpty) {
        throw StateError('disposable anonymous account has no active persona');
      }
      final personalization =
          AssistantProductionComposition.personalizationFacade(
            client: client,
            invocationContext: assistantInvocationContext,
          );
      final sessionRun = AssistantProductionComposition.sessionRunFacade(
        client: client,
        invocationContext: assistantInvocationContext,
        presentationCapabilities: _apiPresentationCapabilities,
      );

      return AssistantApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        session: session,
        preferences: AssistantProductionComposition.preferenceFacet(
          client: client,
          invocationContext: assistantInvocationContext,
        ),
        personalization: personalization,
        sessionRun: sessionRun,
        tasks: AssistantProductionComposition.taskQuery(
          client: client,
          invocationContext: assistantInvocationContext,
        ),
        skillCatalog:
            AssistantProductionComposition.generatedAdapter<
              AssistantSkillCatalogFacet
            >(
              AssistantProductionAdapter.skillCatalog,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        skillSubscriptions:
            AssistantProductionComposition.generatedAdapter<
              AssistantSkillSubscriptionFacet
            >(
              AssistantProductionAdapter.skillSubscription,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        skillUserSettings:
            AssistantProductionComposition.generatedAdapter<
              AssistantSkillUserSettingFacet
            >(
              AssistantProductionAdapter.skillUserSetting,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        skillConsents:
            AssistantProductionComposition.generatedAdapter<
              AssistantSkillConsentFacet
            >(
              AssistantProductionAdapter.skillConsent,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        skillActivities:
            AssistantProductionComposition.generatedAdapter<
              AssistantSkillActivityQuery
            >(
              AssistantProductionAdapter.skillActivity,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        skillDataControlCommands:
            AssistantProductionComposition.generatedAdapter<
              SkillDataControlProcessCommandWriter
            >(
              AssistantProductionAdapter.skillDataControl,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        skillDataControlQueries:
            AssistantProductionComposition.generatedAdapter<
              SkillDataControlProcessQuery
            >(
              AssistantProductionAdapter.skillDataControl,
              client: client,
              invocationContext: assistantInvocationContext,
            ),
        accountLifecycle: accountLifecycle,
      );
    } catch (_) {
      if (session != null && tokenProvider.accessToken != null) {
        try {
          await accountLifecycle.closeAccount(
            CloseAccountCommand(
              clientRequestId: 'assistant-api-cleanup-${session.ownerId}',
            ),
          );
        } catch (_) {
          // Preserve the setup failure; account cleanup is best-effort here.
        }
      }
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final AuthSessionGrant session;
  final AssistantPreferenceFacet preferences;
  final AssistantPersonalizationFacade personalization;
  final AssistantSessionRunComposition sessionRun;
  final AssistantTaskQuery tasks;
  final AssistantSkillCatalogFacet skillCatalog;
  final AssistantSkillSubscriptionFacet skillSubscriptions;
  final AssistantSkillUserSettingFacet skillUserSettings;
  final AssistantSkillConsentFacet skillConsents;
  final AssistantSkillActivityQuery skillActivities;
  final SkillDataControlProcessCommandWriter skillDataControlCommands;
  final SkillDataControlProcessQuery skillDataControlQueries;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  bool _closed = false;

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'assistant-api-cleanup-${session.ownerId}',
        ),
      );
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

AppUiSurface _assistantSurfaceForClientPage(String clientPageId) {
  if (clientPageId == AssistantRequestPageIds.setAssistantPreference ||
      clientPageId == AssistantRequestPageIds.listAssistantPreferences ||
      clientPageId == AssistantRequestPageIds.revokeAssistantPreference ||
      clientPageId == AssistantRequestPageIds.restoreAssistantPreference) {
    return AppUiSurfaces.assistantManagement;
  }
  if (clientPageId == AssistantRequestPageIds.getSkillSubscription) {
    return AppUiSurfaces.personalAssistantDialog;
  }
  if (clientPageId == AssistantRequestPageIds.getAssistantEntry ||
      clientPageId == AssistantRequestPageIds.reportPageContext ||
      clientPageId == AssistantRequestPageIds.createAssistantSession ||
      clientPageId == AssistantRequestPageIds.listAssistantSessions ||
      clientPageId == AssistantRequestPageIds.getAssistantSession ||
      clientPageId == AssistantRequestPageIds.startAssistantRun ||
      clientPageId == AssistantRequestPageIds.getAssistantRun ||
      clientPageId == AssistantRequestPageIds.listSessionTurns ||
      clientPageId == AssistantRequestPageIds.listAssistantTasks) {
    return AppUiSurfaces.personalAssistantDialog;
  }
  if (clientPageId == AssistantRequestPageIds.listSkills ||
      clientPageId == AssistantRequestPageIds.getSkillCatalogItem ||
      clientPageId == AssistantRequestPageIds.listSkillSubscriptions ||
      clientPageId == AssistantRequestPageIds.createSkillSubscription ||
      clientPageId == AssistantRequestPageIds.updateSkillSubscriptionStatus ||
      clientPageId == AssistantRequestPageIds.listSkillUserSettings ||
      clientPageId == AssistantRequestPageIds.getSkillUserSetting ||
      clientPageId == AssistantRequestPageIds.putSkillUserSetting ||
      clientPageId == AssistantRequestPageIds.listConsents ||
      clientPageId == AssistantRequestPageIds.grantSkillConsent ||
      clientPageId == AssistantRequestPageIds.revokeSkillConsent ||
      clientPageId == AssistantRequestPageIds.listSkillActivities ||
      clientPageId == AssistantRequestPageIds.createSkillDataControlRequest ||
      clientPageId == AssistantRequestPageIds.confirmSkillDataControlRequest ||
      clientPageId == AssistantRequestPageIds.getSkillDataControlRequest) {
    return AppUiSurfaces.assistantSkills;
  }
  throw StateError(
    'Unsupported Assistant API contract clientPageId: $clientPageId',
  );
}

AssistantPresentationCapabilitySnapshot _apiPresentationCapabilities(
  AssistantPresentationSurfacePolicy surfacePolicy,
) {
  return AssistantPresentationCapabilitySnapshot(
    surfacePolicy: surfacePolicy,
    viewportClass: AssistantPresentationViewportClass.standard,
    platform: 'api-integration',
    darkTheme: false,
    textScale: 1,
    reducedMotion: false,
    offline: false,
    mediaEnabled: true,
    actionsEnabled: true,
  );
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _AssistantApiClientContext implements CloudClientContextProvider {
  const _AssistantApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'assistant-api-contract',
      deviceActorId: assistantApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
