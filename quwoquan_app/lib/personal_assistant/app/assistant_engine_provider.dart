import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/personal_assistant/api/assistent_api_gateway.dart';
import 'package:quwoquan_app/personal_assistant/config/assistent_configuration_center.dart';
import 'package:quwoquan_app/personal_assistant/cost/assistent_cost_ledger.dart';
import 'package:quwoquan_app/personal_assistant/observability/assistent_alert_dispatcher.dart';
import 'package:quwoquan_app/personal_assistant/observability/assistent_slo_monitor.dart';
import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_health.dart';
import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_policy.dart';
import 'package:quwoquan_app/personal_assistant/providers/assistent_provider_registry.dart';
import 'package:quwoquan_app/personal_assistant/security/assistent_audit_logger.dart';
import 'package:quwoquan_app/personal_assistant/security/assistent_auth_acl.dart';
import 'package:quwoquan_app/personal_assistant/security/assistent_signature_validator.dart';
import 'package:quwoquan_app/personal_assistant/spi/adapters/assistent_feishu_adapter.dart';
import 'package:quwoquan_app/personal_assistant/spi/adapters/assistent_openclaw_adapter.dart';
import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_registry.dart';
import 'package:quwoquan_app/personal_assistant/spi/assistent_adapter_runtime.dart';
import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_store.dart';
import 'package:quwoquan_app/personal_assistant/learning/assistant_learning_service.dart';
import 'package:quwoquan_app/personal_assistant/sync/cloud_stub_sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/local_mock_sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_gateway.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/app/capability_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/app/assistant_runtime.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/skills/skill_manifest.dart';

final assistantRuntimeProvider = Provider<AssistantRuntime>((ref) {
  return AssistantRuntime.createDefault();
});

final assistantGatewayProvider = Provider<AssistantGateway>((ref) {
  return AssistantGateway(ref.watch(assistantRuntimeProvider));
});

final openClawBridgeProvider = Provider<OpenClawBridge>((ref) {
  return OpenClawBridge(
    baseUrl: const String.fromEnvironment(
      'PERSONAL_ASSISTANT_OPENCLAW_BASE_URL',
    ),
    authToken: const String.fromEnvironment(
      'PERSONAL_ASSISTANT_OPENCLAW_TOKEN',
    ),
  );
});

final capabilityGatewayProvider = Provider<CapabilityGateway>((ref) {
  return CapabilityGateway(
    assistantGateway: ref.watch(assistantGatewayProvider),
    openClawBridge: ref.watch(openClawBridgeProvider),
    isPersonalContentAccessGranted: () =>
        ref.read(assistantPersonalContentAccessGrantedProvider),
    isAssistantContentIdentityIndexEnabled: () =>
        ref.read(assistantContentIdentityIndexEnabledProvider),
  );
});

final assistantSkillMarketProvider =
    FutureProvider<List<PersonalAssistantSkillInfo>>((ref) async {
      final gateway = ref.watch(assistantGatewayProvider);
      return gateway.listSkills();
    });

final assistentProviderRegistryProvider = Provider<AssistentProviderRegistry>((
  ref,
) {
  final registry = AssistentProviderRegistry();
  final modelRefs = ref.watch(assistantGatewayProvider).listAvailableModels();
  if (modelRefs.isEmpty) {
    registry.register(
      const AssistentProviderDescriptor(
        id: 'local_heuristic',
        type: AssistentProviderType.llm,
        version: 'v1',
        enabled: true,
        metadata: <String, dynamic>{'costWeight': 0.1, 'latencyWeight': 0.2},
      ),
    );
  } else {
    for (final refId in modelRefs) {
      registry.register(
        AssistentProviderDescriptor(
          id: refId,
          type: AssistentProviderType.llm,
          version: 'v1',
          enabled: true,
          metadata: const <String, dynamic>{
            'costWeight': 1.0,
            'latencyWeight': 1.0,
          },
        ),
      );
    }
  }
  registry.register(
    const AssistentProviderDescriptor(
      id: 'brave',
      type: AssistentProviderType.search,
      version: 'v1',
      enabled: true,
      metadata: <String, dynamic>{'costWeight': 0.8, 'latencyWeight': 0.9},
    ),
  );
  registry.register(
    const AssistentProviderDescriptor(
      id: 'perplexity',
      type: AssistentProviderType.search,
      version: 'v1',
      enabled: true,
      metadata: <String, dynamic>{'costWeight': 1.2, 'latencyWeight': 1.1},
    ),
  );
  return registry;
});

final assistentConfigurationCenterProvider =
    Provider<AssistentConfigurationCenter>((ref) {
      final center = AssistentConfigurationCenter();
      center.update(
        version: 'v1',
        values: <String, dynamic>{
          'slo.maxP95LatencyMs': 2800,
          'slo.minAvailability': 0.985,
          'slo.maxErrorRate': 0.015,
          'alert.suppressSeconds': 180,
          'alert.logEnabled': true,
          'alert.webhookUrl': '',
          'alert.feishuWebhook': '',
          'sync.mode': 'local_mock',
        },
      );
      return center;
    });

final assistentCostLedgerProvider = Provider<AssistentCostLedger>((ref) {
  return AssistentCostLedger();
});

final assistentAuditLoggerProvider = Provider<AssistentAuditLogger>((ref) {
  return AssistentAuditLogger();
});

final assistentAuthAclProvider = Provider<AssistentAuthAcl>((ref) {
  return const AssistentAuthAcl();
});

final assistentProviderPolicyProvider = Provider<AssistentProviderPolicy>((
  ref,
) {
  return const AssistentProviderPolicy();
});

final assistentProviderHealthServiceProvider =
    Provider<AssistentProviderHealthService>((ref) {
      return AssistentProviderHealthService();
    });

final assistentSloMonitorProvider = Provider<AssistentSloMonitor>((ref) {
  final cfg = ref.watch(assistentConfigurationCenterProvider);
  return AssistentSloMonitor(
    defaultTarget: AssistentSloTarget(
      maxP95LatencyMs: cfg.readInt('slo.maxP95LatencyMs', 2800),
      minAvailability: cfg.readDouble('slo.minAvailability', 0.985),
      maxErrorRate: cfg.readDouble('slo.maxErrorRate', 0.015),
    ),
  );
});

final assistentAlertDispatcherProvider = Provider<AssistentAlertDispatcher>((
  ref,
) {
  final cfg = ref.watch(assistentConfigurationCenterProvider);
  return AssistentAlertDispatcher(
    webhookUrl: cfg.readString(
      'alert.webhookUrl',
      const String.fromEnvironment('ASSISTENT_ALERT_WEBHOOK_URL'),
    ),
    feishuBotWebhook: cfg.readString(
      'alert.feishuWebhook',
      const String.fromEnvironment('ASSISTENT_ALERT_FEISHU_WEBHOOK'),
    ),
    suppressWindowSeconds: cfg.readInt(
      'alert.suppressSeconds',
      const int.fromEnvironment(
        'ASSISTENT_ALERT_SUPPRESS_SECONDS',
        defaultValue: 180,
      ),
    ),
    logChannelEnabled: cfg.readBool('alert.logEnabled', true),
  );
});

final assistentApiGatewayProvider = Provider<AssistentApiGateway>((ref) {
  return AssistentApiGateway(
    assistantGateway: ref.watch(assistantGatewayProvider),
    providerRegistry: ref.watch(assistentProviderRegistryProvider),
    providerPolicy: ref.watch(assistentProviderPolicyProvider),
    providerHealthService: ref.watch(assistentProviderHealthServiceProvider),
    sloMonitor: ref.watch(assistentSloMonitorProvider),
    alertDispatcher: ref.watch(assistentAlertDispatcherProvider),
    costLedger: ref.watch(assistentCostLedgerProvider),
    auditLogger: ref.watch(assistentAuditLoggerProvider),
    authAcl: ref.watch(assistentAuthAclProvider),
    adapterRuntime: ref.watch(assistentAdapterRuntimeProvider),
  );
});

final assistentAdapterRegistryProvider = Provider<AssistentAdapterRegistry>((
  ref,
) {
  final registry = AssistentAdapterRegistry();
  final feishuModeRaw = const String.fromEnvironment(
    'ASSISTENT_FEISHU_SIGN_MODE',
    defaultValue: 'hmac_sha256',
  );
  final feishuMode = feishuModeRaw == 'none'
      ? AssistentSignatureMode.none
      : feishuModeRaw == 'token'
      ? AssistentSignatureMode.token
      : AssistentSignatureMode.hmacSha256;
  final openclawModeRaw = const String.fromEnvironment(
    'ASSISTENT_OPENCLAW_SIGN_MODE',
    defaultValue: 'hmac_sha256',
  );
  final openclawMode = openclawModeRaw == 'none'
      ? AssistentSignatureMode.none
      : openclawModeRaw == 'token'
      ? AssistentSignatureMode.token
      : AssistentSignatureMode.hmacSha256;
  registry.register(
    AssistentFeishuAdapter(
      signaturePolicy: AssistentSignaturePolicy(
        mode: feishuMode,
        secret: const String.fromEnvironment('ASSISTENT_FEISHU_SIGN_SECRET'),
        signatureHeader: 'x-lark-signature',
        tokenHeader: 'x-feishu-token',
        timestampHeader: 'x-lark-request-timestamp',
        maxSkewSeconds: const int.fromEnvironment(
          'ASSISTENT_FEISHU_MAX_SKEW_SECONDS',
          defaultValue: 300,
        ),
      ),
    ),
  );
  registry.register(
    AssistentOpenclawAdapter(
      signaturePolicy: AssistentSignaturePolicy(
        mode: openclawMode,
        secret: const String.fromEnvironment('ASSISTENT_OPENCLAW_SIGN_SECRET'),
        signatureHeader: 'x-openclaw-signature',
        tokenHeader: 'x-openclaw-token',
        timestampHeader: 'x-openclaw-timestamp',
        maxSkewSeconds: const int.fromEnvironment(
          'ASSISTENT_OPENCLAW_MAX_SKEW_SECONDS',
          defaultValue: 300,
        ),
      ),
    ),
  );
  return registry;
});

final assistentAdapterRuntimeProvider = Provider<AssistentAdapterRuntime>((
  ref,
) {
  return AssistentAdapterRuntime(ref.watch(assistentAdapterRegistryProvider));
});

final assistentSyncModeProvider = Provider<AssistentSyncMode>((ref) {
  final cfg = ref.watch(assistentConfigurationCenterProvider);
  return AssistentSyncModeParser.parse(
    cfg.readString('sync.mode', 'local_mock'),
  );
});

final assistentSyncAdapterProvider = Provider<AssistentSyncAdapter>((ref) {
  final mode = ref.watch(assistentSyncModeProvider);
  switch (mode) {
    case AssistentSyncMode.localMock:
      return LocalMockSyncAdapter();
    case AssistentSyncMode.cloudStub:
      return const CloudStubSyncAdapter();
  }
});

final assistentSyncGatewayProvider = Provider<AssistentSyncGateway>((ref) {
  final mode = ref.watch(assistentSyncModeProvider);
  final adapter = ref.watch(assistentSyncAdapterProvider);
  return AssistentSyncGateway(adapter, mode);
});

final assistentLearningStoreProvider = Provider<AssistentLearningStore>((ref) {
  return AssistentLearningStore();
});

final assistentLearningServiceProvider = Provider<AssistentLearningService>((
  ref,
) {
  return AssistentLearningService(
    store: ref.watch(assistentLearningStoreProvider),
    syncGateway: ref.watch(assistentSyncGatewayProvider),
  );
});
