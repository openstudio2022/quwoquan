/// Assistant 域 production Remote 适配器（B8 批次阶段 3a 拆分产物）。
///
/// 一个 Remote 类实现 8 个对象级窄 Facet（与 content 域 RemoteContentRepository
/// 同构）；接口与共享类型见 `assistant_facets.dart`。alpha/test 替身位于
/// `test/support/cloud_services/assistant_facets_mock.dart`，production 不可达。
///
/// B8 阶段 3b 错误单轨：读接口失败一律抛经 [CloudErrorMapper] 收口的
/// `CloudException`，不再本地合成 fallback 结果；学习事实以单条幂等 command
/// 追加；遥测类上报（页面上下文）保留结构化降级 ack。
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_session_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_catalog_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart'
    show AssistantDeviceActionExecutionReceipt, AssistantSurfaceCapabilities;
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_runtime_enums.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_retry_policy.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_run_stream_event.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

export 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart'
    show AssistantConsentStore;
export 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';

part 'assistant_repository_consent.dart';
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

typedef AssistantSessionInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// 公开 Remote 类型维持为所有 assistant typed Facet 的唯一 production 装配点。
///
/// 每个 Facet 的直接实现位于同 library 的职责 part 中；此类只组合这些实现与共享
/// transport 基座，不引入方法转发层或第二个公开 repository。
class RemoteAssistantRepository extends _RemoteAssistantRepositoryBase
    with
        _RemoteAssistantSessionRun,
        _RemoteAssistantSkillConsent,
        _RemoteAssistantExperience,
        _RemoteAssistantPreference,
        _RemoteAssistantSearchRun
    implements
        AssistantSessionRunFacet,
        AssistantRunControlFacet,
        AssistantSkillConsentFacet,
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantPreferenceFacet,
        AssistantSearchRunFacet,
        AssistantCreationRunFacet {
  factory RemoteAssistantRepository({
    CloudHttpClient? httpClient,
    AssistantConsentStore? store,
    required GeneratedCloudOperationClient operationClient,
    required AssistantSessionInvocationContextFactory sessionInvocationContext,
    required String consentAccountId,
  }) {
    return RemoteAssistantRepository._(
      httpClient: httpClient,
      store: store,
      sessionQuery: RemoteAssistantSessionQueryAdapter(
        client: operationClient,
        invocationContext: sessionInvocationContext,
      ),
      skillCatalog: RemoteAssistantSkillCatalogAdapter(
        client: operationClient,
        invocationContext: sessionInvocationContext,
      ),
      consentAccountId: consentAccountId,
    );
  }

  RemoteAssistantRepository._({
    super.httpClient,
    super.store,
    required super.sessionQuery,
    required super.skillCatalog,
    required super.consentAccountId,
  });
}

/// 各 Facet 共享的 transport、metadata surface 和解码原语。
///
/// 此基座不声明任何业务 Facet 方法，避免重新聚合对象级职责。
abstract class _RemoteAssistantRepositoryBase {
  _RemoteAssistantRepositoryBase({
    CloudHttpClient? httpClient,
    AssistantConsentStore? store,
    required this._sessionQuery,
    required this._skillCatalog,
    required String consentAccountId,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _store = store ?? AssistantConsentStore(accountId: consentAccountId);

  final CloudHttpClient _httpClient;
  final AssistantConsentStore _store;
  final RemoteAssistantSessionQueryAdapter _sessionQuery;
  final RemoteAssistantSkillCatalogAdapter _skillCatalog;

  static final CloudOperationContract _assistantStreamOperation =
      appCloudOperationContracts[AppCloudOperationIds
          .assistantAssistantRunStreamAssistantRunEvents]!;
  static const CloudRetryPolicy _assistantStreamRetryPolicy =
      CloudRetryPolicy();

  Map<String, String> _headersForSettings({
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantSettings.id,
      routeId: AppUiSurfaces.assistantSettings.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  String _settingsContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.assistantSettings.id,
      operationId: operationId,
    );
  }

  Map<String, String> _headersForNetworkResults({required String operationId}) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      routeId: AppUiSurfaces.globalSearchNetworkResults.routeId,
      operationId: operationId,
      clientPageId: AssistantRequestPageIds.startAssistantRun,
    );
  }

  Map<String, String> _headersForPersonalAssistantDialog({
    required String operationId,
    required String clientPageId,
  }) {
    return CloudRequestHeaders.forSurfaceOperation(
      surfaceId: AppUiSurfaces.personalAssistantDialog.id,
      routeId: AppUiSurfaces.personalAssistantDialog.routeId,
      operationId: operationId,
      clientPageId: clientPageId,
    );
  }

  String _personalAssistantDialogContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.personalAssistantDialog.id,
      operationId: operationId,
    );
  }

  Uri _assistantGetUri(String path, Map<String, String> query) {
    final base = Uri.parse('${CloudRuntimeConfig.gatewayBaseUrl}$path');
    if (query.isEmpty) {
      return base;
    }
    return base.replace(
      queryParameters: <String, String>{
        for (final e in query.entries)
          if (e.value.isNotEmpty) e.key: e.value,
      },
    );
  }

  Uri _assistantUri(String path) {
    return Uri.parse('${CloudRuntimeConfig.gatewayBaseUrl}$path');
  }

  Map<String, dynamic> _decodeAssistantObject(
    http.Response response, {
    required String operationId,
  }) {
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw CloudErrorMapper.fromStatusCode(
        response.statusCode,
        body: response.body,
        requestPath: response.request?.url.path,
      );
    }
    final decoded = response.body.trim().isEmpty
        ? <String, dynamic>{}
        : jsonDecode(response.body);
    return CloudResponseDecoder.asObject(
      decoded,
      context: _personalAssistantDialogContext(operationId: operationId),
    );
  }

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
      operation: AssistantApiMetadata.startAssistantRunOperation,
    );
    final request = AssistantStartRunRequest(
      sessionId: sessionId,
      clientRequestId: requestId,
      intent: intent,
      contextSnapshot: contextSnapshot,
      surfaceCapabilities: AssistantSurfaceCapabilities(
        surfaceId: networkSurface
            ? AppUiSurfaces.globalSearchNetworkResults.id
            : AppUiSurfaces.personalAssistantDialog.id,
        supportedNodeKinds: <String>[
          AssistantPresentationNodeKind.markdown.wireName,
          AssistantPresentationNodeKind.column.wireName,
          AssistantPresentationNodeKind.actionGroup.wireName,
          AssistantPresentationNodeKind.confirmationCard.wireName,
        ],
        viewportClass: 'any',
        platform: CloudRequestHeaders.platform(),
        theme: 'system',
        textScale: 1,
        reducedMotion: false,
        offline: false,
      ),
    );
    final uri = _assistantUri(
      AssistantApiMetadata.startAssistantRunPath(sessionId: sessionId),
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ...(networkSurface
            ? _headersForNetworkResults(
                operationId: AssistantApiMetadata.startAssistantRunOperation,
              )
            : _headersForPersonalAssistantDialog(
                operationId: AssistantApiMetadata.startAssistantRunOperation,
                clientPageId: AssistantRequestPageIds.startAssistantRun,
              )),
        'Idempotency-Key': requestId,
        'Content-Type': 'application/json',
      },
      body: jsonEncode(request.toJson()..remove('sessionId')),
    );
    return AssistantRunEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.startAssistantRunOperation,
      ),
    );
  }
}

final class _AssistantSseFrame {
  const _AssistantSseFrame({required this.event, required this.lastEventId});

  final AssistantStreamEventWire event;
  final String lastEventId;
}

_AssistantSseFrame? _decodeAssistantStreamFrame(String frame) {
  final lines = const LineSplitter().convert(frame);
  final dataLines = <String>[];
  var lastEventId = '';
  for (final rawLine in lines) {
    final line = rawLine.trimRight();
    if (line.startsWith('id:')) {
      lastEventId = line.substring(3).trim();
    } else if (line.startsWith('data:')) {
      dataLines.add(line.substring(5).trimLeft());
    }
  }
  if (dataLines.isEmpty) {
    return null;
  }
  final decoded = jsonDecode(dataLines.join('\n'));
  if (decoded is! Map) {
    return null;
  }
  final envelope = decoded.cast<String, dynamic>();
  const allowedKeys = <String>{
    'schema',
    'eventId',
    'sessionId',
    'runId',
    'seq',
    'eventType',
    'traceId',
    'payload',
    'runtimeFailure',
    'createdAt',
  };
  final unknownKeys = envelope.keys
      .where((key) => !allowedKeys.contains(key))
      .toList(growable: false);
  if (unknownKeys.isNotEmpty) {
    throw FormatException(
      'AssistantStreamEvent contains unknown fields: ${unknownKeys.join(',')}',
    );
  }
  if (envelope['schema'] != 'assistant_stream_event') {
    throw const FormatException(
      'AssistantStreamEvent.schema must be assistant_stream_event',
    );
  }
  for (final field in const <String>[
    'eventId',
    'sessionId',
    'runId',
    'eventType',
    'createdAt',
  ]) {
    final value = envelope[field];
    if (value is! String || value.trim().isEmpty) {
      throw FormatException(
        'AssistantStreamEvent.$field must be a non-empty string',
      );
    }
  }
  final seq = envelope['seq'];
  if (seq is! int || seq <= 0) {
    throw const FormatException(
      'AssistantStreamEvent.seq must be a positive integer',
    );
  }
  final payload = envelope['payload'];
  if (payload is! Map || payload.keys.any((key) => key is! String)) {
    throw const FormatException(
      'AssistantStreamEvent.payload must be an object',
    );
  }
  if (parseAssistantRunStreamEventType(envelope['eventType'] as String) ==
      AssistantRunStreamEventType.unknown) {
    throw FormatException(
      'AssistantStreamEvent.eventType is unsupported: ${envelope['eventType']}',
    );
  }
  return _AssistantSseFrame(
    event: AssistantStreamEventWire.fromJson(envelope),
    lastEventId: lastEventId,
  );
}

bool _isAssistantTerminalStreamEvent(AssistantStreamEventWire event) {
  return parseAssistantRunStreamEventType(event.eventType.wireName).isTerminal;
}

bool _isAssistantStreamRetryable(CloudException error) {
  return switch (error.type) {
    CloudErrorType.timeout ||
    CloudErrorType.network ||
    CloudErrorType.rateLimited ||
    CloudErrorType.server => true,
    _ => false,
  };
}

void _debugAssistantRepository(String message) {
  if (!kDebugMode && !kProfileMode) {
    return;
  }
  debugPrint('[assistant-repository] $message');
}
