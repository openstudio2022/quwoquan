import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/assistant/api/assistant_api_gateway.dart';
import 'package:quwoquan_app/assistant/config/assistant_configuration_center.dart';
import 'package:quwoquan_app/assistant/infrastructure/openclaw_bridge.dart';
import 'package:quwoquan_app/assistant/cost/assistant_cost_ledger.dart';
import 'package:quwoquan_app/assistant/learning/assistant_learning_runtime.dart';
import 'package:quwoquan_app/assistant/observability/assistant_observability_runtime.dart';
import 'package:quwoquan_app/assistant/providers/assistant_provider_runtime.dart';
import 'package:quwoquan_app/assistant/runtime/assistant_runtime.dart';
import 'package:quwoquan_app/assistant/security/assistant_security_runtime.dart';
import 'package:quwoquan_app/assistant/spi/assistant_adapter_runtime.dart';
import 'package:quwoquan_app/assistant/sync/assistant_sync.dart';
import 'package:quwoquan_app/assistant/skills/skill_manifest.dart';

import 'assistant_edge_service.dart';
import 'assistant_gateway.dart';
import 'capability_gateway.dart';

final assistantEdgeServiceProvider = Provider<AssistantEdgeService>((ref) {
  return AssistantEdgeService.createDefault();
});

final assistantRuntimeProvider = Provider<AssistantRuntime>((ref) {
  return ref.watch(assistantEdgeServiceProvider).runtime;
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

final assistantProviderRegistryProvider = Provider<AssistantProviderRegistry>((
  ref,
) {
  final registry = AssistantProviderRegistry();
  final modelRefs = ref.watch(assistantGatewayProvider).listAvailableModels();
  if (modelRefs.isEmpty) {
    registry.register(
      const AssistantProviderDescriptor(
        id: 'local_heuristic',
        type: AssistantProviderType.llm,
        version: 'v1',
        enabled: true,
        metadata: <String, dynamic>{'costWeight': 0.1, 'latencyWeight': 0.2},
      ),
    );
  } else {
    for (final refId in modelRefs) {
      registry.register(
        AssistantProviderDescriptor(
          id: refId,
          type: AssistantProviderType.llm,
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
    const AssistantProviderDescriptor(
      id: 'brave',
      type: AssistantProviderType.search,
      version: 'v1',
      enabled: true,
      metadata: <String, dynamic>{'costWeight': 0.8, 'latencyWeight': 0.9},
    ),
  );
  registry.register(
    const AssistantProviderDescriptor(
      id: 'perplexity',
      type: AssistantProviderType.search,
      version: 'v1',
      enabled: true,
      metadata: <String, dynamic>{'costWeight': 1.2, 'latencyWeight': 1.1},
    ),
  );
  return registry;
});

final assistantConfigurationCenterProvider =
    Provider<AssistantConfigurationCenter>((ref) {
      final center = AssistantConfigurationCenter();
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

final assistantCostLedgerProvider = Provider<AssistantCostLedger>((ref) {
  return AssistantCostLedger();
});

final assistantAuditLoggerProvider = Provider<AssistantAuditLogger>((ref) {
  return AssistantAuditLogger();
});

final assistantAuthAclProvider = Provider<AssistantAuthAcl>((ref) {
  return const AssistantAuthAcl();
});

final assistantProviderPolicyProvider = Provider<AssistantProviderPolicy>((
  ref,
) {
  return const AssistantProviderPolicy();
});

final assistantProviderHealthServiceProvider =
    Provider<AssistantProviderHealthService>((ref) {
      return AssistantProviderHealthService();
    });

final assistantSloMonitorProvider = Provider<AssistantSloMonitor>((ref) {
  final cfg = ref.watch(assistantConfigurationCenterProvider);
  return AssistantSloMonitor(
    defaultTarget: AssistantSloTarget(
      maxP95LatencyMs: cfg.readInt('slo.maxP95LatencyMs', 2800),
      minAvailability: cfg.readDouble('slo.minAvailability', 0.985),
      maxErrorRate: cfg.readDouble('slo.maxErrorRate', 0.015),
    ),
  );
});

final assistantAlertDispatcherProvider = Provider<AssistantAlertDispatcher>((
  ref,
) {
  final cfg = ref.watch(assistantConfigurationCenterProvider);
  return AssistantAlertDispatcher(
    webhookUrl: cfg.readString(
      'alert.webhookUrl',
      _assistantAlertWebhookUrl(),
    ),
    feishuBotWebhook: cfg.readString(
      'alert.feishuWebhook',
      _assistantAlertFeishuWebhook(),
    ),
    suppressWindowSeconds: cfg.readInt(
      'alert.suppressSeconds',
      _assistantAlertSuppressSeconds(),
    ),
    logChannelEnabled: cfg.readBool('alert.logEnabled', true),
  );
});

final assistantApiGatewayProvider = Provider<AssistantApiGateway>((ref) {
  return AssistantApiGateway(
    assistantGateway: ref.watch(assistantGatewayProvider),
    providerRegistry: ref.watch(assistantProviderRegistryProvider),
    providerPolicy: ref.watch(assistantProviderPolicyProvider),
    providerHealthService: ref.watch(assistantProviderHealthServiceProvider),
    sloMonitor: ref.watch(assistantSloMonitorProvider),
    alertDispatcher: ref.watch(assistantAlertDispatcherProvider),
    costLedger: ref.watch(assistantCostLedgerProvider),
    auditLogger: ref.watch(assistantAuditLoggerProvider),
    authAcl: ref.watch(assistantAuthAclProvider),
    adapterRuntime: ref.watch(assistantAdapterRuntimeProvider),
    authToken: _assistantGatewayToken(),
    autoDisableDuration: Duration(minutes: _assistantAutoDisableMinutes()),
  );
});

final assistantAdapterRegistryProvider = Provider<AssistantAdapterRegistry>((
  ref,
) {
  final registry = AssistantAdapterRegistry();
  final feishuModeRaw = _assistantFeishuSignMode();
  final feishuMode = feishuModeRaw == 'none'
      ? AssistantSignatureMode.none
      : feishuModeRaw == 'token'
      ? AssistantSignatureMode.token
      : AssistantSignatureMode.hmacSha256;
  final openclawModeRaw = _assistantOpenclawSignMode();
  final openclawMode = openclawModeRaw == 'none'
      ? AssistantSignatureMode.none
      : openclawModeRaw == 'token'
      ? AssistantSignatureMode.token
      : AssistantSignatureMode.hmacSha256;
  registry.register(
    AssistantFeishuAdapter(
      signaturePolicy: AssistantSignaturePolicy(
        mode: feishuMode,
        secret: _assistantFeishuSignSecret(),
        signatureHeader: 'x-lark-signature',
        tokenHeader: 'x-feishu-token',
        timestampHeader: 'x-lark-request-timestamp',
        maxSkewSeconds: _assistantFeishuMaxSkewSeconds(),
      ),
    ),
  );
  registry.register(
    AssistantOpenclawAdapter(
      signaturePolicy: AssistantSignaturePolicy(
        mode: openclawMode,
        secret: _assistantOpenclawSignSecret(),
        signatureHeader: 'x-openclaw-signature',
        tokenHeader: 'x-openclaw-token',
        timestampHeader: 'x-openclaw-timestamp',
        maxSkewSeconds: _assistantOpenclawMaxSkewSeconds(),
      ),
    ),
  );
  return registry;
});

final assistantAdapterRuntimeProvider = Provider<AssistantAdapterRuntime>((
  ref,
) {
  return AssistantAdapterRuntime(ref.watch(assistantAdapterRegistryProvider));
});

final assistantSyncModeProvider = Provider<AssistantSyncMode>((ref) {
  final cfg = ref.watch(assistantConfigurationCenterProvider);
  return AssistantSyncModeParser.parse(
    cfg.readString('sync.mode', 'local_mock'),
  );
});

final assistantSyncAdapterProvider = Provider<AssistantSyncAdapter>((ref) {
  final mode = ref.watch(assistantSyncModeProvider);
  switch (mode) {
    case AssistantSyncMode.localMock:
      return LocalMockSyncAdapter();
    case AssistantSyncMode.cloudStub:
      return const CloudStubSyncAdapter();
  }
});

final assistantSyncGatewayProvider = Provider<AssistantSyncGateway>((ref) {
  final mode = ref.watch(assistantSyncModeProvider);
  final adapter = ref.watch(assistantSyncAdapterProvider);
  return AssistantSyncGateway(adapter, mode);
});

final assistantLearningStoreProvider = Provider<AssistantLearningStore>((ref) {
  return AssistantLearningStore();
});

final assistantLearningServiceProvider = Provider<AssistantLearningService>((
  ref,
) {
  return AssistantLearningService(
    store: ref.watch(assistantLearningStoreProvider),
    syncGateway: ref.watch(assistantSyncGatewayProvider),
  );
});

String _assistantAlertWebhookUrl() {
  return const String.fromEnvironment('ASSISTANT_ALERT_WEBHOOK_URL');
}

String _assistantAlertFeishuWebhook() {
  return const String.fromEnvironment('ASSISTANT_ALERT_FEISHU_WEBHOOK');
}

int _assistantAlertSuppressSeconds() {
  const value = int.fromEnvironment(
    'ASSISTANT_ALERT_SUPPRESS_SECONDS',
    defaultValue: 180,
  );
  return value;
}

String _assistantGatewayToken() {
  return const String.fromEnvironment('PERSONAL_ASSISTANT_GATEWAY_TOKEN');
}

int _assistantAutoDisableMinutes() {
  const value = int.fromEnvironment(
    'ASSISTANT_ALERT_AUTO_DISABLE_MINUTES',
    defaultValue: 10,
  );
  return value;
}

String _assistantFeishuSignMode() {
  const value = String.fromEnvironment('ASSISTANT_FEISHU_SIGN_MODE');
  return value.isEmpty ? 'hmac_sha256' : value;
}

String _assistantOpenclawSignMode() {
  const value = String.fromEnvironment('ASSISTANT_OPENCLAW_SIGN_MODE');
  return value.isEmpty ? 'hmac_sha256' : value;
}

String _assistantFeishuSignSecret() {
  return const String.fromEnvironment('ASSISTANT_FEISHU_SIGN_SECRET');
}

String _assistantOpenclawSignSecret() {
  return const String.fromEnvironment('ASSISTANT_OPENCLAW_SIGN_SECRET');
}

int _assistantFeishuMaxSkewSeconds() {
  const value = int.fromEnvironment(
    'ASSISTANT_FEISHU_MAX_SKEW_SECONDS',
    defaultValue: 300,
  );
  return value;
}

int _assistantOpenclawMaxSkewSeconds() {
  const value = int.fromEnvironment(
    'ASSISTANT_OPENCLAW_MAX_SKEW_SECONDS',
    defaultValue: 300,
  );
  return value;
}
