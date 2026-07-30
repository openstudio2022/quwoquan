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
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_conversation_query_remote.dart';
import 'package:quwoquan_app/cloud/remote/assistant/assistant_skill_catalog_remote.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
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
part 'assistant_repository_conversation_run.dart';
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

typedef AssistantConversationInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// 公开 Remote 类型维持为所有 assistant typed Facet 的唯一 production 装配点。
///
/// 每个 Facet 的直接实现位于同 library 的职责 part 中；此类只组合这些实现与共享
/// transport 基座，不引入方法转发层或第二个公开 repository。
class RemoteAssistantRepository extends _RemoteAssistantRepositoryBase
    with
        _RemoteAssistantConversationRun,
        _RemoteAssistantSkillConsent,
        _RemoteAssistantExperience,
        _RemoteAssistantPreferenceFact,
        _RemoteAssistantXiaoquSearch
    implements
        AssistantConversationRunFacet,
        AssistantSkillConsentFacet,
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantPreferenceFactFacet,
        AssistantXiaoquSearchFacet,
        AssistantCreationSuggestFacet {
  factory RemoteAssistantRepository({
    CloudHttpClient? httpClient,
    AssistantConsentStore? store,
    required GeneratedCloudOperationClient operationClient,
    required AssistantConversationInvocationContextFactory
    conversationInvocationContext,
    required String consentActorScope,
  }) {
    return RemoteAssistantRepository._(
      httpClient: httpClient,
      store: store,
      conversationQuery: RemoteAssistantConversationQueryAdapter(
        client: operationClient,
        invocationContext: conversationInvocationContext,
      ),
      skillCatalog: RemoteAssistantSkillCatalogAdapter(
        client: operationClient,
        invocationContext: conversationInvocationContext,
      ),
      consentActorScope: consentActorScope,
    );
  }

  RemoteAssistantRepository._({
    super.httpClient,
    super.store,
    required super.conversationQuery,
    required super.skillCatalog,
    required super.consentActorScope,
  });
}

/// 各 Facet 共享的 transport、metadata surface 和解码原语。
///
/// 此基座不声明任何业务 Facet 方法，避免重新聚合对象级职责。
abstract class _RemoteAssistantRepositoryBase {
  _RemoteAssistantRepositoryBase({
    CloudHttpClient? httpClient,
    AssistantConsentStore? store,
    required this._conversationQuery,
    required this._skillCatalog,
    required String consentActorScope,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _store = store ?? AssistantConsentStore(actorScope: consentActorScope);

  final CloudHttpClient _httpClient;
  final AssistantConsentStore _store;
  final RemoteAssistantConversationQueryAdapter _conversationQuery;
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
      clientPageId: AssistantRequestPageIds.searchXiaoquResults,
    );
  }

  String _networkResultsContext({required String operationId}) {
    return CloudRequestHeaders.contextForSurfaceOperation(
      surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
      operationId: operationId,
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

  List<Map<String, dynamic>> _decodeItemsMap(
    Object? decoded, {
    required String context,
  }) {
    if (decoded is List) {
      return decoded
          .whereType<Map>()
          .map((row) => row.cast<String, dynamic>())
          .toList(growable: false);
    }
    final object = CloudResponseDecoder.asObject(decoded, context: context);
    final raw =
        (object['items'] as List?)
            ?.whereType<Map>()
            .map((row) => row.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    return raw;
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
    'conversationId',
    'turnId',
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
    'conversationId',
    'turnId',
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

String _assistantDebugSnippet(String value, {int maxLength = 120}) {
  final normalized = value.replaceAll(RegExp(r'\s+'), ' ').trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return '${normalized.substring(0, maxLength)}...';
}
