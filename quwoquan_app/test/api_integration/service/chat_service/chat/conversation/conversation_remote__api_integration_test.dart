// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/conversation-list-source-switch/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/commercial-remote-only-message-system/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/group-home-chat-info-contract/spec.md#gwt-001
// spec_ref: specs/feature-tree/chat-conversation/group-creation-member-management/group-settings/spec.md#gwt-003
// readiness_case: conversation_create_conversation_app_api
// readiness_case: conversation_list_conversations_app_api
// readiness_case: conversation_get_conversation_app_api
// readiness_case: conversation_update_conversation_title_app_api
// readiness_case: conversation_get_group_home_app_api
// readiness_case: conversation_list_conversation_timestamps_app_api
// readiness_case: conversation_batch_get_conversations_app_api
// readiness_case: conversation_update_group_governance_settings_app_api
// readiness_case: conversation_dissolve_conversation_app_api

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/generated/chat/chat_errors.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/adapters/conversation_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/chat_api_contract_harness.dart';
import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');

void main() {
  ChatApiContractHarness? harness;
  _ConversationRemotes? validRemotes;
  _ConversationRemotes? invalidRemotes;
  late String conversationId;

  ChatApiContractHarness activeHarness() {
    return harness ??
        (throw StateError('ChatApiContractHarness setup did not complete'));
  }

  setUpAll(() async {
    final createdHarness = await ChatApiContractHarness.create();
    harness = createdHarness;
    final identity = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final created = await createdHarness.repository.createConversation(
      type: 'group',
      title: 'API contract conversation $identity',
      maxGroupSize: 20,
      idempotencyKey: 'conversation-suite-$identity',
    );
    conversationId = created.conversationId;
    if (conversationId.trim().isEmpty) {
      throw StateError('CreateConversation returned an empty conversationId');
    }
    validRemotes = _ConversationRemotes.create(
      harness: createdHarness,
      accessToken: createdHarness.session.accessToken,
    );
    invalidRemotes = _ConversationRemotes.create(
      harness: createdHarness,
      accessToken: 'invalid-chat-conversation-api-token',
    );
  });
  tearDownAll(() async {
    validRemotes?.close();
    invalidRemotes?.close();
    await harness?.close();
  });

  test('generated client 创建会话按同一命令身份幂等重放', () async {
    final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final idempotencyKey = 'conversation-create-$nonce';

    final created = await activeHarness().repository.createConversation(
      type: 'group',
      title: 'API contract conversation',
      maxGroupSize: 20,
      idempotencyKey: idempotencyKey,
    );
    final replayed = await activeHarness().repository.createConversation(
      type: 'group',
      title: 'API contract conversation',
      maxGroupSize: 20,
      idempotencyKey: idempotencyKey,
    );

    expect(created.conversationId, isNotEmpty);
    expect(replayed.conversationId, created.conversationId);
  });

  test('generated client 通过 production Remote 返回会话列表', () async {
    final stopwatch = Stopwatch()..start();
    final conversations = await activeHarness().repository.listConversations(
      limit: 5,
    );
    stopwatch.stop();

    expect(stopwatch.elapsedMilliseconds, lessThan(800));
    expect(conversations, isNotEmpty);
    expect(conversations.first.id, isNotEmpty);
    expect(conversations.first.type, isNotEmpty);
  });

  test('generated client 通过 production Remote 返回完整会话', () async {
    final conversation = await activeHarness().repository.getConversation(
      conversationId,
    );

    expect(conversation.id, conversationId);
    expect(conversation.type, isNotEmpty);
    expect(conversation.status, 'active');
    expect(conversation.createdAt, isNotNull);
  });

  test('generated client 更新标题后由 production Remote 权威读回', () async {
    final title =
        'API contract title ${DateTime.now().toUtc().microsecondsSinceEpoch}';

    await activeHarness().repository.updateConversationTitle(
      conversationId,
      title,
    );
    final updated = await activeHarness().repository.getConversation(
      conversationId,
    );

    expect(updated.title, title);
  });

  test('generated client 通过 production Remote 读取同源 GroupHome', () async {
    final home = await activeHarness().repository.getGroupHome(conversationId);

    expect(home.conversationId, conversationId);
    expect(home.title, isNotEmpty);
    expect(home.memberCount, greaterThanOrEqualTo(1));
    expect(home.originType, isNotEmpty);
    expect(home.accessMode.wireName, isNotEmpty);
    expect(home.postingPolicy.wireName, isNotEmpty);
    final events = await activeHarness().telemetry.waitForEvents(
      minimumCount: 1,
    );
    expect(
      events.any(
        (event) =>
            event.canonicalOperationId ==
                AppCloudOperationIds.chatConversationGetGroupHome &&
            event.succeeded,
      ),
      isTrue,
    );
  });

  test('GetGroupHome 不存在的 conversationId 保留 canonical error', () async {
    await expectLater(
      activeHarness().repository.getGroupHome(
        'nonexistent_conv_group_home_00000',
      ),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              'CHAT.USER.conversation_not_found',
            )
            .having(
              (error) => error.sourceOperationId,
              'sourceOperationId',
              AppCloudOperationIds.chatConversationGetGroupHome,
            ),
      ),
    );
  });

  test('不存在的 conversationId 保留 canonical error', () async {
    await expectLater(
      activeHarness().repository.getConversation('nonexistent_conv_00000'),
      throwsA(
        isA<CloudException>()
            .having((error) => error.statusCode, 'statusCode', 404)
            .having(
              (error) => error.code,
              'code',
              'CHAT.USER.conversation_not_found',
            ),
      ),
    );
  });

  test('production Remote 返回非空时间戳索引与批量会话并保留鉴权失败', () async {
    final remotes = validRemotes!;
    final unauthorized = invalidRemotes!;

    final timestamps = await remotes.query.listConversationTimestamps(
      ChatListConversationTimestampsQuery(),
    );
    final timestamp = timestamps.items.singleWhere(
      (item) => item.conversationId == conversationId,
    );
    expect(timestamp.type, 'group');
    expect(timestamp.updatedAt.isAfter(DateTime.utc(2000)), isTrue);

    final batch = await remotes.query.batchGetConversations(
      ChatBatchGetConversationsQuery(conversationIds: <String>[conversationId]),
    );
    expect(batch.items, hasLength(1));
    expect(batch.items.single.id, conversationId);
    expect(batch.items.single.status, 'active');

    await _expectCanonicalFailure(
      unauthorized.query.listConversationTimestamps(
        ChatListConversationTimestampsQuery(),
      ),
      operationId:
          AppCloudOperationIds.chatConversationListConversationTimestamps,
      statusCode: anyOf(401, 403),
      code: ChatErrorCode.unauthorized.code,
    );
    await _expectCanonicalFailure(
      unauthorized.query.batchGetConversations(
        ChatBatchGetConversationsQuery(
          conversationIds: <String>[conversationId],
        ),
      ),
      operationId: AppCloudOperationIds.chatConversationBatchGetConversations,
      statusCode: anyOf(401, 403),
      code: ChatErrorCode.unauthorized.code,
    );

    final events = await activeHarness().telemetry.waitForEvents(
      minimumCount: 4,
    );
    _expectOperationTelemetry(
      events,
      operationId:
          AppCloudOperationIds.chatConversationListConversationTimestamps,
      successCount: 1,
      failureStatus: anyOf(401, 403),
    );
    _expectOperationTelemetry(
      events,
      operationId: AppCloudOperationIds.chatConversationBatchGetConversations,
      successCount: 1,
      failureStatus: anyOf(401, 403),
    );
  });

  test('群治理设置同 key 重放后由 production Remote 权威回读', () async {
    final remotes = validRemotes!;
    final identity = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final command = ChatUpdateGroupGovernanceSettingsCommand(
      conversationId: conversationId,
      nameEditableByAdminOnly: true,
    );
    final idempotencyKey = 'conversation-governance-$identity';

    final first = await remotes.commands.updateGroupGovernanceSettings(
      command,
      idempotencyKey: idempotencyKey,
    );
    final replay = await remotes.commands.updateGroupGovernanceSettings(
      command,
      idempotencyKey: idempotencyKey,
    );
    expect(first.toWire(), replay.toWire());
    expect(first.nameEditableByAdminOnly, isTrue);

    final readback = await remotes.query.getConversation(
      ChatGetConversationQuery(conversationId: conversationId),
    );
    expect(readback.nameEditableByAdminOnly, isTrue);
    expect(readback.updatedAt, first.updatedAt);

    await _expectCanonicalFailure(
      remotes.commands.updateGroupGovernanceSettings(
        ChatUpdateGroupGovernanceSettingsCommand(
          conversationId: 'nonexistent_conv_governance_00000',
          nameEditableByAdminOnly: true,
        ),
        idempotencyKey: 'conversation-governance-missing-$identity',
      ),
      operationId:
          AppCloudOperationIds.chatConversationUpdateGroupGovernanceSettings,
      statusCode: 404,
      code: ChatErrorCode.conversationNotFound.code,
    );

    final events = await activeHarness().telemetry.waitForEvents(
      minimumCount: 4,
    );
    _expectOperationTelemetry(
      events,
      operationId:
          AppCloudOperationIds.chatConversationUpdateGroupGovernanceSettings,
      successCount: 2,
      failureStatus: 404,
    );
  });

  test('解散会话同 key 重放且列表权威收敛', () async {
    final remotes = validRemotes!;
    final identity = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    final created = await activeHarness().repository.createConversation(
      type: 'group',
      title: 'API dissolve conversation $identity',
      maxGroupSize: 20,
      idempotencyKey: 'conversation-dissolve-create-$identity',
    );
    final dissolvedId = created.conversationId;
    expect(dissolvedId, isNotEmpty);

    final command = ChatDissolveConversationCommand(
      conversationId: dissolvedId,
    );
    final idempotencyKey = 'conversation-dissolve-$identity';
    final first = await remotes.commands.dissolveConversation(
      command,
      idempotencyKey: idempotencyKey,
    );
    final replay = await remotes.commands.dissolveConversation(
      command,
      idempotencyKey: idempotencyKey,
    );
    expect(first.toWire(), replay.toWire());
    expect(first.status, isNotEmpty);

    final readback = await activeHarness().repository.listConversations(
      limit: 20,
    );
    expect(readback.map((item) => item.id), contains(conversationId));
    expect(readback.map((item) => item.id), isNot(contains(dissolvedId)));

    await _expectCanonicalFailure(
      remotes.commands.dissolveConversation(
        ChatDissolveConversationCommand(
          conversationId: 'nonexistent_conv_dissolve_00000',
        ),
        idempotencyKey: 'conversation-dissolve-missing-$identity',
      ),
      operationId: AppCloudOperationIds.chatConversationDissolveConversation,
      statusCode: 404,
      code: ChatErrorCode.conversationNotFound.code,
    );

    final events = await activeHarness().telemetry.waitForEvents(
      minimumCount: 5,
    );
    _expectOperationTelemetry(
      events,
      operationId: AppCloudOperationIds.chatConversationDissolveConversation,
      successCount: 2,
      failureStatus: 404,
    );
  });
}

final class _ConversationRemotes {
  const _ConversationRemotes._({
    required this.query,
    required this.commands,
    required this._httpClient,
  });

  final RemoteChatConversationQuery query;
  final RemoteChatConversationCommandWriter commands;
  final CloudHttpClient _httpClient;

  factory _ConversationRemotes.create({
    required ChatApiContractHarness harness,
    required String accessToken,
  }) {
    final httpClient = CloudHttpClient(
      authTokenProvider: _StaticAccessTokenProvider(accessToken),
    );
    final client = buildGeneratedCloudOperationClient(
      httpClient: httpClient,
      clientContextProvider: const _ChatConversationApiClientContext(),
      telemetrySink: harness.telemetry.sink,
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

    CloudOperationInvocationContext context(
      AppUiSurface surface,
      String clientPageId, {
      String? idempotencyKey,
    }) => CloudOperationInvocationContext(
      surfaceId: surface.id,
      routeId: surface.routeId,
      clientPageId: clientPageId,
      idempotencyKey: idempotencyKey,
      actor: CloudOperationActorContext(
        accountId: harness.session.ownerId,
        personaId: harness.session.activePersona?.personaId,
        deviceActorId: chatApiContractDeviceId,
      ),
    );

    return _ConversationRemotes._(
      httpClient: httpClient,
      query: RemoteChatConversationQuery(
        client: client,
        invocationContext: (clientPageId) {
          final surface = switch (clientPageId) {
            ChatRequestPageIds.getConversation => AppUiSurfaces.chatDetail,
            ChatRequestPageIds.getGroupHome => AppUiSurfaces.chatAnnouncement,
            _ => AppUiSurfaces.chatList,
          };
          return context(surface, clientPageId);
        },
      ),
      commands: RemoteChatConversationCommandWriter(
        client: client,
        invocationContext: (clientPageId, idempotencyKey) {
          final surface = switch (clientPageId) {
            ChatRequestPageIds.createConversation =>
              AppUiSurfaces.startGroupChat,
            ChatRequestPageIds.updateConversationTitle =>
              AppUiSurfaces.chatSettings,
            ChatRequestPageIds.updateAnnouncement =>
              AppUiSurfaces.chatAnnouncement,
            _ => AppUiSurfaces.chatManage,
          };
          return context(surface, clientPageId, idempotencyKey: idempotencyKey);
        },
      ),
    );
  }

  void close() => _httpClient.close();
}

final class _StaticAccessTokenProvider implements CloudAuthTokenProvider {
  const _StaticAccessTokenProvider(this.accessToken);

  final String accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _ChatConversationApiClientContext
    implements CloudClientContextProvider {
  const _ChatConversationApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'chat-conversation-api-contract',
      deviceActorId: chatApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}

Future<void> _expectCanonicalFailure(
  Future<Object?> future, {
  required String operationId,
  required Object statusCode,
  required String code,
}) {
  return expectLater(
    future,
    throwsA(
      isA<CloudException>()
          .having((error) => error.statusCode, 'statusCode', statusCode)
          .having((error) => error.code, 'code', code)
          .having(
            (error) => error.sourceOperationId,
            'sourceOperationId',
            operationId,
          ),
    ),
  );
}

void _expectOperationTelemetry(
  List<ProductionCloudOperationTelemetryEvent> events, {
  required String operationId,
  required int successCount,
  required Object failureStatus,
}) {
  final matching = events
      .where((event) => event.canonicalOperationId == operationId)
      .toList(growable: false);
  final succeeded = matching.where((event) => event.succeeded).toList();
  expect(succeeded, hasLength(successCount));
  expect(succeeded.every((event) => event.statusCode == 200), isTrue);
  final failed = matching.where((event) => !event.succeeded).single;
  expect(failed.statusCode, failureStatus);
  expect(
    matching.every(
      (event) => event.requestId.isNotEmpty && event.traceId.isNotEmpty,
    ),
    isTrue,
  );
}
