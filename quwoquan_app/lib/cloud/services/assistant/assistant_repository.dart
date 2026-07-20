/// Assistant 域 production Remote 适配器（B8 批次阶段 3a 拆分产物）。
///
/// 一个 Remote 类实现 8 个对象级窄 Facet（与 content 域 RemoteContentRepository
/// 同构）；接口与共享类型见 `assistant_facets.dart`。alpha/test 替身位于
/// `test/support/cloud_services/assistant_facets_mock.dart`，production 不可达。
///
/// B8 阶段 3b 错误单轨：读接口失败一律抛经 [CloudErrorMapper] 收口的
/// `CloudException`，不再本地合成 fallback 结果；批量学习上报保留部分成功
/// 语义但不静默单条失败；遥测类上报（页面上下文）保留结构化降级 ack。
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
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/cloud/runtime/transport/cloud_retry_policy.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

export 'package:quwoquan_app/cloud/services/assistant/assistant_consent_store.dart'
    show AssistantConsentStore;
export 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';

class RemoteAssistantRepository
    implements
        AssistantConversationRunFacet,
        AssistantSkillSubscriptionFacet,
        AssistantSkillConsentFacet,
        AssistantLearningAppendFacet,
        AssistantPersonalizationFacet,
        AssistantPersonalDataFacet,
        AssistantPreferenceFactFacet,
        AssistantXiaoquSearchFacet,
        AssistantCreationSuggestFacet {
  RemoteAssistantRepository({
    CloudHttpClient? httpClient,
    AssistantConsentStore? store,
    required String consentActorScope,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _store = store ?? AssistantConsentStore(actorScope: consentActorScope);

  final CloudHttpClient _httpClient;
  final AssistantConsentStore _store;

  static final CloudOperationContract _assistantStreamOperation =
      appCloudOperationContracts[AppCloudOperationIds
          .assistantAssistantRunStreamAssistantRunEvents]!;
  static const CloudRetryPolicy _assistantStreamRetryPolicy =
      CloudRetryPolicy();

  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async {
    // 失败关闭：policy 拉取失败不再合成 learningSyncEnabled=true 的本地
    // fallback；调用方必须按"学习同步关闭"处理。
    const path = AssistantApiMetadata.getPolicyPath;
    try {
      final uri = _assistantGetUri(path, {
        if (policyVersionHint.trim().isNotEmpty)
          'policyVersionHint': policyVersionHint.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getPolicyOperation,
          clientPageId: AssistantRequestPageIds.getPolicy,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId: AssistantApiMetadata.getPolicyOperation,
              ),
            );
      if (decoded.isEmpty) {
        throw const FormatException(
          'assistant policy snapshot response is empty',
        );
      }
      return AssistantPolicyView.fromJson(decoded);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    // 批量部分成功语义：单条失败记录后计入 rejected；全部尝试条目失败时
    // 抛出最后一次结构化异常，部分成功返回 acceptedCount<count 的 ack 由
    // 调用方重试。
    const path = AssistantApiMetadata.reportInteractionEventPath;
    final accepted = <InteractionEvent>[];
    var attempted = 0;
    CloudException? lastFailure;
    for (final event in events) {
      final eventId = event.eventId.trim();
      final runId = event.runId.trim();
      if (eventId.isEmpty || runId.isEmpty) {
        continue;
      }
      attempted += 1;
      try {
        final uri = _assistantUri(path);
        final response = await _httpClient.post(
          uri,
          headers: <String, String>{
            ..._headersForPersonalAssistantDialog(
              operationId: AssistantApiMetadata.reportInteractionEventOperation,
              clientPageId: AssistantRequestPageIds.reportInteractionEvent,
            ),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(event.toJson()),
        );
        if (response.statusCode >= 200 && response.statusCode < 300) {
          accepted.add(event);
        } else {
          lastFailure = CloudErrorMapper.fromStatusCode(
            response.statusCode,
            body: response.body,
            requestPath: path,
          );
          developer.log(
            'interaction event rejected eventId=$eventId status=${response.statusCode}',
            name: 'AssistantLearningAppend',
            error: lastFailure,
          );
        }
      } catch (error) {
        lastFailure = CloudErrorMapper.fromException(error, requestPath: path);
        developer.log(
          'interaction event report failed eventId=$eventId',
          name: 'AssistantLearningAppend',
          error: error,
        );
      }
    }
    final failure = lastFailure;
    if (attempted > 0 && accepted.isEmpty && failure != null) {
      throw failure;
    }
    return AssistantInteractionReportBatchAck.fromJson(<String, dynamic>{
      'accepted': accepted.length == events.length,
      'acceptedCount': accepted.length,
      'count': events.length,
      'resource': 'interaction_event_batch',
    });
  }

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async {
    // 与 reportInteractionEvents 同一批量部分成功语义。
    const path = AssistantApiMetadata.reportScorecardPath;
    final accepted = <Scorecard>[];
    var attempted = 0;
    CloudException? lastFailure;
    for (final scorecard in scorecards) {
      final scoreId = scorecard.scoreId.trim();
      final eventId = scorecard.eventId.trim();
      if (scoreId.isEmpty || eventId.isEmpty) {
        continue;
      }
      attempted += 1;
      try {
        final uri = _assistantUri(path);
        final response = await _httpClient.post(
          uri,
          headers: <String, String>{
            ..._headersForPersonalAssistantDialog(
              operationId: AssistantApiMetadata.reportScorecardOperation,
              clientPageId: AssistantRequestPageIds.reportScorecard,
            ),
            'Content-Type': 'application/json',
          },
          body: jsonEncode(scorecard.toJson()),
        );
        if (response.statusCode >= 200 && response.statusCode < 300) {
          accepted.add(scorecard);
        } else {
          lastFailure = CloudErrorMapper.fromStatusCode(
            response.statusCode,
            body: response.body,
            requestPath: path,
          );
          developer.log(
            'scorecard rejected eventId=$eventId status=${response.statusCode}',
            name: 'AssistantLearningAppend',
            error: lastFailure,
          );
        }
      } catch (error) {
        lastFailure = CloudErrorMapper.fromException(error, requestPath: path);
        developer.log(
          'scorecard report failed eventId=$eventId',
          name: 'AssistantLearningAppend',
          error: error,
        );
      }
    }
    final failure = lastFailure;
    if (attempted > 0 && accepted.isEmpty && failure != null) {
      throw failure;
    }
    return AssistantScorecardReportBatchAck.fromJson(<String, dynamic>{
      'accepted': accepted.length == scorecards.length,
      'acceptedCount': accepted.length,
      'count': scorecards.length,
      'resource': 'scorecard_batch',
    });
  }

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

  @override
  Future<List<AssistantSkillConsent>> listConsents() async {
    final uri = _assistantUri(AssistantApiMetadata.listConsentsPath);
    final decoded = await _httpClient.getJson(
      uri,
      headers: _headersForSettings(
        operationId: AssistantApiMetadata.listConsentsOperation,
        clientPageId: AssistantRequestPageIds.listConsents,
      ),
    );
    final object = decoded is List
        ? <String, dynamic>{'items': decoded}
        : CloudResponseDecoder.asObject(
            decoded,
            context: _settingsContext(
              operationId: AssistantApiMetadata.listConsentsOperation,
            ),
          );
    final rawItems =
        (object['items'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    final consents = rawItems
        .map(AssistantSkillConsent.fromJson)
        .where((item) => item.skillId.isNotEmpty)
        .toList(growable: false);
    await _store.save(consents);
    return consents;
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    final path = AssistantApiMetadata.grantSkillConsentPath(skillId: skillId);
    final uri = _assistantUri(path);
    final decoded = await _httpClient.postJson(
      uri,
      headers: _headersForSettings(
        operationId: AssistantApiMetadata.grantSkillConsentOperation,
        clientPageId: AssistantRequestPageIds.grantSkillConsent,
      ),
      body: <String, dynamic>{'grantedScope': grantedScope},
    );
    try {
      final object = CloudResponseDecoder.asObject(
        decoded,
        context: _settingsContext(
          operationId: AssistantApiMetadata.grantSkillConsentOperation,
        ),
      );
      final payload =
          (object['consent'] as Map?)?.cast<String, dynamic>() ?? object;
      final consent = AssistantSkillConsent.fromJson(payload);
      if (consent.skillId != skillId || !consent.granted) {
        throw const FormatException(
          'assistant consent grant response is not authoritative',
        );
      }
      await _store.upsert(consent);
      return consent;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) async {
    final uri = _assistantUri(
      AssistantApiMetadata.revokeSkillConsentPath(skillId: skillId),
    );
    await _httpClient.deleteJson(
      uri,
      headers: _headersForSettings(
        operationId: AssistantApiMetadata.revokeSkillConsentOperation,
        clientPageId: AssistantRequestPageIds.revokeSkillConsent,
      ),
    );
    await _store.revoke(skillId);
  }

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
    Map<String, dynamic>? contextSnapshot,
  }) async {
    // 不再本地合成"假搜索摘要"；空 query、非 2xx、解码失败或空回显一律抛
    // 结构化 CloudException，由消费页走错误态。
    const path = AssistantApiMetadata.searchXiaoquResultsPath;
    final trimmedQuery = query.trim();
    if (trimmedQuery.isEmpty) {
      throw CloudErrorMapper.fromException(
        ArgumentError.value(query, 'query', 'must not be empty'),
        requestPath: path,
      );
    }
    try {
      final uri = _assistantUri(path);
      final response = await _httpClient.post(
        uri,
        headers: <String, String>{
          ..._headersForNetworkResults(
            operationId: AssistantApiMetadata.searchXiaoquResultsOperation,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(
          AssistantSearchXiaoquRequestWire(
            userQuery: trimmedQuery,
            searchIntensity: searchIntensity,
            sourceSurfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
            fromGlobalSearch: true,
          ).toJson()..addAll(
            contextSnapshot == null
                ? const <String, dynamic>{}
                : <String, dynamic>{'contextSnapshot': contextSnapshot},
          ),
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _networkResultsContext(
                operationId: AssistantApiMetadata.searchXiaoquResultsOperation,
              ),
            );
      final result = AssistantSearchResultView.fromJson(decoded);
      if (result.queryEcho.isEmpty &&
          (result.summary?.trim().isEmpty ?? true)) {
        throw const FormatException(
          'xiaoqu search result is missing queryEcho and summary',
        );
      }
      return result;
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<PageContextAck> reportPageContext({
    required AssistantOpenContext context,
    String? userAction,
    List<Map<String, dynamic>> userActions = const <Map<String, dynamic>>[],
  }) async {
    final snapshot = assistantContextSnapshotFromOpenContext(
      context,
      operationId: AssistantApiMetadata.reportPageContextOperation,
    );
    final pageType = assistantPageTypeForSource(context.source);
    final objectType = context.objectType?.trim() ?? '';
    final objectId = context.entityId?.trim() ?? '';
    final businessObjects = <Map<String, dynamic>>[
      if (objectType.isNotEmpty && objectId.isNotEmpty)
        <String, dynamic>{'objectType': objectType, 'objectId': objectId},
    ];
    try {
      final response = await _httpClient.post(
        _assistantUri(AssistantApiMetadata.reportPageContextPath),
        headers: <String, String>{
          ..._headersForPersonalAssistantDialog(
            operationId: AssistantApiMetadata.reportPageContextOperation,
            clientPageId: AssistantRequestPageIds.reportPageContext,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(
          AssistantReportPageContextRequestWire(
            pageType: pageType,
            businessObjects: businessObjects,
            userAction: userAction,
            userActions: userActions.isEmpty ? null : userActions,
          ).toJson()..addAll(<String, dynamic>{'contextSnapshot': snapshot}),
        ),
      );
      if (response.statusCode >= 200 && response.statusCode < 300) {
        final decoded = response.body.trim().isEmpty
            ? <String, dynamic>{}
            : CloudResponseDecoder.asObject(
                jsonDecode(response.body),
                context: _personalAssistantDialogContext(
                  operationId: AssistantApiMetadata.reportPageContextOperation,
                ),
              );
        return PageContextAck.fromJson(decoded);
      }
      developer.log(
        'page context report rejected status=${response.statusCode}',
        name: 'AssistantPersonalization',
        error: CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: AssistantApiMetadata.reportPageContextPath,
        ),
      );
    } catch (error) {
      // 页面上下文上报是遥测类 best-effort：记录后返回 accepted=false 的
      // 结构化降级 ack，不阻断半屏入口。
      developer.log(
        'page context report failed pageType=$pageType',
        name: 'AssistantPersonalization',
        error: error,
      );
    }
    return PageContextAck(
      accepted: false,
      contextKey: 'fallback:$pageType',
      expiresAt: DateTime.now()
          .toUtc()
          .add(const Duration(minutes: 5))
          .toIso8601String(),
    );
  }

  @override
  Future<AssistantEntryPersonalizationView> getEntryPersonalization({
    required AssistantOpenContext context,
  }) async {
    // 失败不再伪造 personalized 数据；UI 层（half sheet）以自己的静态默认
    // 欢迎区作为空态展示。
    const path = AssistantApiMetadata.getEntryPersonalizationPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        'source': context.source.name,
        'pageType': assistantPageTypeForSource(context.source),
        if ((context.tab ?? '').trim().isNotEmpty) 'tab': context.tab!.trim(),
        if ((context.dimension ?? '').trim().isNotEmpty)
          'dimension': context.dimension!.trim(),
        if ((context.entityId ?? '').trim().isNotEmpty)
          'objectId': context.entityId!.trim(),
        if ((context.objectType ?? '').trim().isNotEmpty)
          'objectType': context.objectType!.trim(),
        'experienceLevel': context.experienceLevel.name,
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getEntryPersonalizationOperation,
          clientPageId: AssistantRequestPageIds.getEntryPersonalization,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId:
                    AssistantApiMetadata.getEntryPersonalizationOperation,
              ),
            );
      return AssistantEntryPersonalizationView.fromJson(decoded);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<SuggestedActionListView> getSuggestedActions({
    required AssistantOpenContext context,
  }) async {
    const path = AssistantApiMetadata.getSuggestedActionsPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        'pageType': assistantPageTypeForSource(context.source),
        if ((context.entityId ?? '').trim().isNotEmpty)
          'objectId': context.entityId!.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.getSuggestedActionsOperation,
          clientPageId: AssistantRequestPageIds.getSuggestedActions,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId: AssistantApiMetadata.getSuggestedActionsOperation,
              ),
            );
      return SuggestedActionListView.fromJson(decoded);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = kAssistantListPageDefaultLimit,
    String? status,
  }) async {
    const path = AssistantApiMetadata.listAssistantTasksPath;
    try {
      final uri = _assistantGetUri(path, {
        'limit': '$limit',
        if (status != null && status.trim().isNotEmpty) 'status': status.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
          clientPageId: AssistantRequestPageIds.listAssistantTasks,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listAssistantTasksOperation,
        ),
      );
      return rows
          .map(AssistantUserTaskView.fromJson)
          .where((row) => row.taskId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantPreferenceFact> setAssistantPreference({
    required AssistantPreferenceScope scope,
    String conversationId = '',
    required AssistantPreferenceKind kind,
    required String value,
    required AssistantPreferenceSourceType sourceType,
  }) {
    const path = AssistantApiMetadata.setAssistantPreferencePath;
    return _postAssistantPreference(
      path: path,
      operationId: AssistantApiMetadata.setAssistantPreferenceOperation,
      clientPageId: AssistantRequestPageIds.setAssistantPreference,
      body: <String, dynamic>{
        'scope': scope.wireName,
        if (conversationId.trim().isNotEmpty)
          'conversationId': conversationId.trim(),
        'kind': kind.wireName,
        'value': value.trim(),
        'sourceType': sourceType.wireName,
      },
    );
  }

  @override
  Future<List<AssistantPreferenceFact>> listAssistantPreferences({
    AssistantPreferenceScope? scope,
    String conversationId = '',
    AssistantPreferenceStatus status = AssistantPreferenceStatus.active,
  }) async {
    const path = AssistantApiMetadata.listAssistantPreferencesPath;
    try {
      final uri = _assistantGetUri(path, <String, String>{
        if (scope != null) 'scope': scope.wireName,
        if (conversationId.trim().isNotEmpty)
          'conversationId': conversationId.trim(),
        'status': status.wireName,
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listAssistantPreferencesOperation,
          clientPageId: AssistantRequestPageIds.listAssistantPreferences,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId:
                    AssistantApiMetadata.listAssistantPreferencesOperation,
              ),
            );
      return AssistantPreferenceFactListView.fromJson(decoded).items
          .where((fact) => fact.preferenceId.trim().isNotEmpty)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantPreferenceFact> revokeAssistantPreference({
    required String preferenceId,
  }) {
    final path = AssistantApiMetadata.revokeAssistantPreferencePath(
      preferenceId: preferenceId.trim(),
    );
    return _postAssistantPreference(
      path: path,
      operationId: AssistantApiMetadata.revokeAssistantPreferenceOperation,
      clientPageId: AssistantRequestPageIds.revokeAssistantPreference,
    );
  }

  @override
  Future<AssistantPreferenceFact> restoreAssistantPreference({
    required String preferenceId,
  }) {
    final path = AssistantApiMetadata.restoreAssistantPreferencePath(
      preferenceId: preferenceId.trim(),
    );
    return _postAssistantPreference(
      path: path,
      operationId: AssistantApiMetadata.restoreAssistantPreferenceOperation,
      clientPageId: AssistantRequestPageIds.restoreAssistantPreference,
    );
  }

  Future<AssistantPreferenceFact> _postAssistantPreference({
    required String path,
    required String operationId,
    required String clientPageId,
    Map<String, dynamic>? body,
  }) async {
    try {
      final response = await _httpClient.post(
        _assistantUri(path),
        headers: <String, String>{
          ..._headersForPersonalAssistantDialog(
            operationId: operationId,
            clientPageId: clientPageId,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(body ?? const <String, dynamic>{}),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = CloudResponseDecoder.asObject(
        jsonDecode(response.body),
        context: _personalAssistantDialogContext(operationId: operationId),
      );
      final fact = AssistantPreferenceFact.fromJson(decoded);
      if (fact.preferenceId.trim().isEmpty) {
        throw const FormatException(
          'assistant preference response is missing preferenceId',
        );
      }
      return fact;
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = kAssistantSkillCatalogDefaultLimit,
  }) async {
    const path = AssistantApiMetadata.listSkillsPath;
    try {
      final uri = _assistantGetUri(path, {'limit': '$limit'});
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listSkillsOperation,
          clientPageId: AssistantRequestPageIds.listSkills,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listSkillsOperation,
        ),
      );
      return rows
          .map(AssistantSkillCatalogItemView.fromJson)
          .where((row) => row.skillId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<AssistantCreationSuggestResponse> suggestCreationAssistance({
    required AssistantCreationSuggestRequest request,
  }) async {
    try {
      final response = await _httpClient.post(
        _assistantUri(AssistantApiMetadata.suggestCreationAssistancePath),
        headers: <String, String>{
          ..._headersForPersonalAssistantDialog(
            operationId:
                AssistantApiMetadata.suggestCreationAssistanceOperation,
            clientPageId: AssistantRequestPageIds.suggestCreationAssistance,
          ),
          'Content-Type': 'application/json',
        },
        body: jsonEncode(request.toJson()),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        return const AssistantCreationSuggestResponse(
          suggestedTagRefs: <String>[],
          suggestedHomepages: <AssistantSuggestedHomepageView>[],
          available: false,
          unavailableReason: 'request_failed',
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : CloudResponseDecoder.asObject(
              jsonDecode(response.body),
              context: _personalAssistantDialogContext(
                operationId:
                    AssistantApiMetadata.suggestCreationAssistanceOperation,
              ),
            );
      return AssistantCreationSuggestResponse.fromJson(decoded);
    } catch (error) {
      // available=false + unavailableReason 是契约内合法的结构化不可用
      // 响应（创作助手为可选增强），记录后降级，不吞异常细节。
      developer.log(
        'creation assistance suggest failed',
        name: 'AssistantCreationSuggest',
        error: error,
      );
      return const AssistantCreationSuggestResponse(
        suggestedTagRefs: <String>[],
        suggestedHomepages: <AssistantSuggestedHomepageView>[],
        available: false,
        unavailableReason: 'request_failed',
      );
    }
  }

  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    const path = AssistantApiMetadata.listSkillSubscriptionsPath;
    try {
      final uri = _assistantGetUri(path, {
        'limit': '$limit',
        if (status.trim().isNotEmpty) 'status': status.trim(),
      });
      final response = await _httpClient.get(
        uri,
        headers: _headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.listSkillSubscriptionsOperation,
          clientPageId: AssistantRequestPageIds.listSkillSubscriptions,
        ),
      );
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw CloudErrorMapper.fromStatusCode(
          response.statusCode,
          body: response.body,
          requestPath: path,
        );
      }
      final decoded = response.body.trim().isEmpty
          ? <String, dynamic>{}
          : jsonDecode(response.body);
      final rows = _decodeItemsMap(
        decoded,
        context: _personalAssistantDialogContext(
          operationId: AssistantApiMetadata.listSkillSubscriptionsOperation,
        ),
      );
      return rows
          .map(SkillSubscriptionWire.fromJson)
          .where((row) => row.subscriptionId.isNotEmpty)
          .take(limit)
          .toList(growable: false);
    } on CloudException {
      rethrow;
    } catch (error) {
      throw CloudErrorMapper.fromException(error, requestPath: path);
    }
  }

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
  }) async {
    final response = await _httpClient.post(
      _assistantUri(AssistantApiMetadata.createSkillSubscriptionPath),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.createSkillSubscriptionOperation,
          clientPageId: AssistantRequestPageIds.createSkillSubscription,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'skillId': skillId,
        'domainId': domainId,
        'tagRefs': tagRefs,
        'searchQueryPlan': <String, dynamic>{
          'rawText': rawText,
          'queries': queries.isEmpty ? <String>[rawText] : queries,
        },
        'trigger': <String, dynamic>{'type': 'cron', 'cron': cron},
        'destination': const <String, dynamic>{'destinationType': 'user'},
      }),
    );
    return SkillSubscriptionWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createSkillSubscriptionOperation,
      ),
    );
  }

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
  }) async {
    final response = await _httpClient.patch(
      _assistantUri(
        AssistantApiMetadata.updateSkillSubscriptionStatusPath(
          subscriptionId: subscriptionId,
        ),
      ),
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId:
              AssistantApiMetadata.updateSkillSubscriptionStatusOperation,
          clientPageId: AssistantRequestPageIds.updateSkillSubscriptionStatus,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'status': status}),
    );
    return SkillSubscriptionWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId:
            AssistantApiMetadata.updateSkillSubscriptionStatusOperation,
      ),
    );
  }

  @override
  Future<AssistantConversationWire> createAssistantConversation({
    String summary = '',
  }) async {
    final uri = _assistantUri(
      AssistantApiMetadata.createAssistantConversationPath,
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.createAssistantConversationOperation}',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId:
              AssistantApiMetadata.createAssistantConversationOperation,
          clientPageId: AssistantRequestPageIds.createAssistantConversation,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{'summary': summary}),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.createAssistantConversationOperation}',
    );
    final conversation = AssistantConversationWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.createAssistantConversationOperation,
      ),
    );
    _debugAssistantRepository(
      'conversation decoded id=${conversation.conversationId}',
    );
    return conversation;
  }

  @override
  Future<AssistantConversationWire> getAssistantConversation({
    required String conversationId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(
        AssistantApiMetadata.getAssistantConversationPath(
          conversationId: conversationId,
        ),
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantConversationOperation,
        clientPageId: AssistantRequestPageIds.getAssistantConversation,
      ),
    );
    return AssistantConversationWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantConversationOperation,
      ),
    );
  }

  @override
  Future<AssistantConversationListPage> listAssistantConversations({
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final response = await _httpClient.get(
      _assistantGetUri(
        AssistantApiMetadata.listAssistantConversationsPath,
        <String, String>{
          'limit': '$limit',
          if (cursor.trim().isNotEmpty) 'cursor': cursor.trim(),
        },
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.listAssistantConversationsOperation,
        clientPageId: AssistantRequestPageIds.listAssistantConversations,
      ),
    );
    return AssistantConversationListPage.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.listAssistantConversationsOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnListView> listConversationTurns({
    required String conversationId,
    int limit = kAssistantListPageDefaultLimit,
    String cursor = '',
  }) async {
    final response = await _httpClient.get(
      _assistantGetUri(
        AssistantApiMetadata.listConversationTurnsPath(
          conversationId: conversationId,
        ),
        <String, String>{
          'limit': '$limit',
          if (cursor.trim().isNotEmpty) 'cursor': cursor.trim(),
        },
      ),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.listConversationTurnsOperation,
        clientPageId: AssistantRequestPageIds.listConversationTurns,
      ),
    );
    return AssistantTurnListView.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.listConversationTurnsOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> cancelAssistantRun({
    required String runId,
  }) async {
    final uri = _assistantUri(
      AssistantApiMetadata.cancelAssistantRunPath(runId: runId),
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.cancelAssistantRunOperation}',
    );
    final response = await _httpClient.post(
      uri,
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.cancelAssistantRunOperation,
        clientPageId: AssistantRequestPageIds.cancelAssistantRun,
      ),
    );
    return AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.cancelAssistantRunOperation,
      ),
    );
  }

  @override
  Future<AssistantTurnEnvelopeWire> startAssistantRun({
    required String conversationId,
    required String text,
    String turnType = 'user',
    String skillId = '',
    String domainId = '',
  }) async {
    final uri = _assistantUri(
      AssistantApiMetadata.startAssistantRunPath(
        conversationId: conversationId,
      ),
    );
    _debugAssistantRepository(
      'POST $uri operation=${AssistantApiMetadata.startAssistantRunOperation} '
      'conversationId=$conversationId text="${_assistantDebugSnippet(text)}"',
    );
    final response = await _httpClient.post(
      uri,
      headers: <String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.startAssistantRunOperation,
          clientPageId: AssistantRequestPageIds.startAssistantRun,
        ),
        'Content-Type': 'application/json',
      },
      body: jsonEncode(<String, dynamic>{
        'turnType': turnType,
        'skillId': skillId,
        'domainId': domainId,
        'input': <String, dynamic>{'text': text},
        'trigger': const <String, dynamic>{'type': 'user_message'},
      }),
    );
    _debugAssistantRepository(
      'response status=${response.statusCode} operation=${AssistantApiMetadata.startAssistantRunOperation}',
    );
    final turn = AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.startAssistantRunOperation,
      ),
    );
    _debugAssistantRepository(
      'turn decoded conversationId=${turn.conversationId} turnId=${turn.turnId} traceId=${turn.traceId}',
    );
    return turn;
  }

  @override
  Future<AssistantTurnEnvelopeWire> getAssistantRun({
    required String runId,
  }) async {
    final response = await _httpClient.get(
      _assistantUri(AssistantApiMetadata.getAssistantRunPath(runId: runId)),
      headers: _headersForPersonalAssistantDialog(
        operationId: AssistantApiMetadata.getAssistantRunOperation,
        clientPageId: AssistantRequestPageIds.getAssistantRun,
      ),
    );
    return AssistantTurnEnvelopeWire.fromJson(
      _decodeAssistantObject(
        response,
        operationId: AssistantApiMetadata.getAssistantRunOperation,
      ),
    );
  }

  @override
  Stream<AssistantStreamEventWire> watchAssistantRunEvents({
    required String runId,
  }) async* {
    final maxAttempts = _assistantStreamOperation.maxAttempts;
    if (maxAttempts < 1 ||
        _assistantStreamOperation.retryMode != 'idempotent') {
      throw StateError(
        'StreamAssistantRunEvents generated reliability contract is invalid',
      );
    }
    var lastSeq = 0;
    var lastEventId = '';
    for (var attempt = 1; attempt <= maxAttempts; attempt++) {
      var terminalEventObserved = false;
      try {
        await for (final frame in _openAssistantRunEventStream(
          runId: runId,
          lastEventId: lastEventId,
        )) {
          final event = frame.event;
          if (event.seq <= lastSeq) {
            continue;
          }
          lastSeq = event.seq;
          if (frame.lastEventId.isNotEmpty) {
            lastEventId = frame.lastEventId;
          }
          terminalEventObserved =
              terminalEventObserved || _isAssistantTerminalStreamEvent(event);
          yield event;
          if (terminalEventObserved) {
            return;
          }
        }
      } on CloudException catch (error) {
        if (!_isAssistantStreamRetryable(error) || attempt == maxAttempts) {
          rethrow;
        }
      } on FormatException {
        rethrow;
      } catch (error, stackTrace) {
        _debugAssistantRepository(
          'stream transport interrupted runId=$runId attempt=$attempt '
          'lastSeq=$lastSeq errorType=${error.runtimeType}',
        );
        if (attempt == maxAttempts) {
          Error.throwWithStackTrace(
            CloudErrorMapper.fromException(
              error,
              requestPath: AssistantApiMetadata.streamAssistantRunEventsPath(
                runId: runId,
              ),
            ),
            stackTrace,
          );
        }
      }
      if (terminalEventObserved) {
        return;
      }
      if (attempt == maxAttempts) {
        throw CloudErrorMapper.fromStatusCode(
          503,
          requestPath: AssistantApiMetadata.streamAssistantRunEventsPath(
            runId: runId,
          ),
        );
      }
      await Future<void>.delayed(
        _assistantStreamRetryPolicy.delayFor(attempt: attempt - 1),
      );
    }
  }

  Stream<_AssistantSseFrame> _openAssistantRunEventStream({
    required String runId,
    required String lastEventId,
  }) async* {
    final path = AssistantApiMetadata.streamAssistantRunEventsPath(
      runId: runId,
    );
    final uri = _assistantGetUri(path, <String, String>{
      if (lastEventId.isNotEmpty) 'resumeToken': lastEventId,
    });
    _debugAssistantRepository(
      'GET $uri operation=${AssistantApiMetadata.streamAssistantRunEventsOperation} runId=$runId',
    );
    final request = http.Request('GET', uri)
      ..headers.addAll(<String, String>{
        ..._headersForPersonalAssistantDialog(
          operationId: AssistantApiMetadata.streamAssistantRunEventsOperation,
          clientPageId: AssistantRequestPageIds.streamAssistantRunEvents,
        ),
        if (lastEventId.isNotEmpty) 'Last-Event-ID': lastEventId,
      });
    final response = await _httpClient.send(request);
    _debugAssistantRepository(
      'stream response status=${response.statusCode} runId=$runId',
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      // StreamedResponse 无同步 body；仅按状态码映射结构化异常。
      throw CloudErrorMapper.fromStatusCode(
        response.statusCode,
        requestPath: AssistantApiMetadata.streamAssistantRunEventsPath(
          runId: runId,
        ),
      );
    }
    final buffer = StringBuffer();
    await for (final piece in response.stream.transform(utf8.decoder)) {
      buffer.write(piece);
      var current = buffer.toString().replaceAll('\r\n', '\n');
      var splitIndex = current.indexOf('\n\n');
      while (splitIndex >= 0) {
        final frame = current.substring(0, splitIndex);
        final decoded = _decodeAssistantStreamFrame(frame);
        if (decoded != null) {
          _debugAssistantRepository(
            'sse event type=${decoded.event.eventType} '
            'seq=${decoded.event.seq} runId=$runId '
            'skill=${decoded.event.payload['skillId'] ?? ''} '
            'tool=${_assistantToolNameFromPayload(decoded.event.payload)}',
          );
          yield decoded;
        }
        current = current.substring(splitIndex + 2);
        splitIndex = current.indexOf('\n\n');
      }
      buffer
        ..clear()
        ..write(current);
    }
    final trailing = buffer.toString().trim();
    if (trailing.isNotEmpty) {
      final decoded = _decodeAssistantStreamFrame(trailing);
      if (decoded != null) {
        yield decoded;
      }
    }
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
  return _AssistantSseFrame(
    event: AssistantStreamEventWire.fromJson(envelope),
    lastEventId: lastEventId,
  );
}

bool _isAssistantTerminalStreamEvent(AssistantStreamEventWire event) {
  return switch (event.eventType) {
    'turn_completed' || 'turn_failed' || 'turn_cancelled' => true,
    _ => false,
  };
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

String _assistantToolNameFromPayload(Map<String, dynamic> payload) {
  final raw = payload['toolUse'];
  if (raw is Map) {
    return (raw['toolName'] ?? '').toString().trim();
  }
  return '';
}
