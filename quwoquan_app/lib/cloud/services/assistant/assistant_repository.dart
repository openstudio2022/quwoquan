/// Assistant 域 production Remote 适配器（B8 批次阶段 3a 拆分产物）。
///
/// 一个 Remote 类实现 8 个对象级窄 Facet（与 content 域 RemoteContentRepository
/// 同构）；接口与共享类型见 `assistant_facets.dart`。alpha/test 替身位于
/// `test/support/cloud_services/assistant_facets_mock.dart`，production 不可达。
///
/// B8 阶段 3b 错误单轨：读接口失败一律由 generated runtime 映射为结构化
/// Cloud error，不再本地合成 fallback 结果；学习事实以单条幂等 command
/// 追加；遥测类上报（页面上下文）保留结构化降级 ack。
library;

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/assistant/capabilities/assistant_presentation_capability_catalog.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_core_remote.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_run_stream_event.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

export 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart'
    show AssistantConsentStore;
export 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';

part 'assistant_repository_session_run.dart';
part 'assistant_repository_experience.dart';
part 'assistant_repository_preferences.dart';
part 'assistant_repository_search.dart';

String _requireAssistantCommandRequestId(
  String value, {
  required String operation,
}) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(
      value,
      'clientRequestId',
      '$operation requires a stable client request identity',
    );
  }
  return normalized;
}

/// 公开 Remote 类型维持为所有 assistant typed Facet 的唯一 production 装配点。
///
/// 每个 Facet 的直接实现位于同 library 的职责 part 中；此类只组合这些实现与共享
/// transport 基座，不引入方法转发层或第二个公开 repository。
class RemoteAssistantRepository extends _RemoteAssistantRepositoryBase
    with
        _RemoteAssistantSessionRun,
        _RemoteAssistantExperience,
        _RemoteAssistantPreference,
        _RemoteAssistantSearchRun
    implements
        AssistantSessionRunFacet,
        AssistantRunControlFacet,
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantPreferenceFacet,
        AssistantSearchRunFacet,
        AssistantCreationRunFacet {
  factory RemoteAssistantRepository({
    required GeneratedCloudOperationClient operationClient,
    required AssistantInvocationContextFactory invocationContext,
    required AssistantPresentationCapabilitySnapshotFactory
    presentationCapabilities,
  }) {
    return RemoteAssistantRepository._(
      RemoteAssistantCoreAdapter(
        client: operationClient,
        invocationContext: invocationContext,
      ),
      presentationCapabilities,
    );
  }

  RemoteAssistantRepository._(super._core, super._presentationCapabilities);
}

/// 各 Facet 共享的 generated-client 核心适配器。
///
/// 此基座不声明任何业务 Facet 方法，避免重新聚合对象级职责。
abstract class _RemoteAssistantRepositoryBase {
  _RemoteAssistantRepositoryBase(this._core, this._presentationCapabilities);

  final RemoteAssistantCoreAdapter _core;
  final AssistantPresentationCapabilitySnapshotFactory
  _presentationCapabilities;

  /// [StartAssistantRun] 的唯一 HTTP 写入口。回答、搜索与创作辅助只通过
  /// generated tagged union 区分 intent，不再拥有独立路由或 decoder。
  Future<AssistantRunEnvelopeWire> _startAssistantRunIntent({
    required String sessionId,
    required String clientRequestId,
    required AssistantRunIntent intent,
    AssistantContextSnapshot? contextSnapshot,
    bool networkSurface = false,
  }) async {
    final requestId = _requireAssistantCommandRequestId(
      clientRequestId,
      operation: AppCloudOperationIds.assistantAssistantRunStartAssistantRun,
    );
    final surfacePolicy = networkSurface
        ? AssistantPresentationSurfacePolicy.network
        : AssistantPresentationSurfacePolicy.personal;
    final capabilitySnapshot = _presentationCapabilities(surfacePolicy);
    if (capabilitySnapshot.surfacePolicy != surfacePolicy) {
      throw StateError(
        'Assistant presentation capability factory returned the wrong surface policy',
      );
    }
    final request = AssistantStartRunRequest(
      sessionId: sessionId,
      clientRequestId: requestId,
      intent: intent,
      contextSnapshot: contextSnapshot,
      surfaceCapabilities: AssistantSurfaceCapabilities(
        surfaceId: networkSurface
            ? AppUiSurfaces.globalSearchNetworkResults.id
            : AppUiSurfaces.personalAssistantDialog.id,
        supportedNodeKinds: capabilitySnapshot.supportedNodeWireNames,
        supportedActionIntents: capabilitySnapshot.supportedActionIntents,
        viewportClass: capabilitySnapshot.viewportClass.wireName,
        platform: capabilitySnapshot.platform,
        theme: capabilitySnapshot.themeWireName,
        textScale: capabilitySnapshot.textScale,
        reducedMotion: capabilitySnapshot.reducedMotion,
        offline: capabilitySnapshot.offline,
      ),
    );
    return _core.startRun(
      request: request,
      idempotencyKey: requestId,
      networkSurface: networkSurface,
    );
  }
}

bool _isAssistantTerminalStreamEvent(AssistantStreamEventWire event) {
  return parseAssistantRunStreamEventType(event.eventType.wireName).isTerminal;
}

void _debugAssistantRepository(String message) {
  if (!kDebugMode && !kProfileMode) {
    return;
  }
  debugPrint('[assistant-repository] $message');
}
