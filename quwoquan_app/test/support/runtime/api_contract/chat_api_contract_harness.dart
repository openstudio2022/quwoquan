import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/service/chat_service/chat/chat_inbox_view/adapters/chat_inbox_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/adapters/conversation_user_state_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/application/public/conversation_user_state_command_writer.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/application/public/message_receipt_fact_query.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'production_cloud_operation_telemetry_evidence.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const _apiBase = String.fromEnvironment('API_CONTRACT_BASE_URL');
const chatApiContractDeviceId = 'chat-api-contract-device';

/// Real generated-client -> production Remote composition -> process harness.
///
/// There is no raw HTTP test path or substitute transport in this harness.
final class ChatApiContractHarness {
  ChatApiContractHarness._({
    required this._httpClient,
    required this.telemetry,
    required this.repository,
    required this.messageCommands,
    required this.inbox,
    required this.userStateCommands,
    required this.receipts,
    required this._accountLifecycle,
    required this.session,
  });

  static Future<ChatApiContractHarness> create() async {
    if (_apiBase.isEmpty) {
      throw StateError('L3: ${_apiContractEnv.toUpperCase()}_BASE_URL not set');
    }
    final tokenProvider = _MutableAccessTokenProvider();
    final httpClient = CloudHttpClient(authTokenProvider: tokenProvider);
    const clientContext = _ChatApiClientContext();
    final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
      clientContextProvider: clientContext,
    );
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

    try {
      final accountSessions = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.appShell.id,
          routeId: AppUiSurfaces.appShell.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            deviceActorId: chatApiContractDeviceId,
          ),
        ),
      );
      final session = await accountSessions.loginAnonymous(
        LoginAnonymousCommand(
          installId:
              'chat-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          deviceFingerprintHash:
              'chat-api-contract-${DateTime.now().microsecondsSinceEpoch}',
          platform: 'web',
          appVersion: 'api-integration',
        ),
      );
      tokenProvider.accessToken = session.accessToken;

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
          accountId: session.ownerId,
          personaId: session.activePersona?.personaId,
          deviceActorId: chatApiContractDeviceId,
        ),
      );

      return ChatApiContractHarness._(
        httpClient: httpClient,
        telemetry: telemetry,
        repository: ChatProductionComposition.repository(
          client: client,
          invocationContext: invocationContext,
        ),
        messageCommands: ChatProductionComposition.messageCommandWriter(
          client: client,
          invocationContext: invocationContext,
        ),
        inbox: RemoteChatInboxQuery(
          client: client,
          invocationContext: (clientPageId) =>
              invocationContext(AppUiSurfaces.chatList, clientPageId),
        ),
        userStateCommands: RemoteChatConversationUserStateCommandWriter(
          client: client,
          invocationContext: (clientPageId, idempotencyKey) {
            final surface = clientPageId == ChatRequestPageIds.markAsRead
                ? AppUiSurfaces.chatDetail
                : AppUiSurfaces.chatSettings;
            return invocationContext(
              surface,
              clientPageId,
              idempotencyKey: idempotencyKey,
            );
          },
        ),
        receipts: ChatProductionComposition.messageReceiptFactQuery(
          client: client,
          invocationContext: invocationContext,
        ),
        accountLifecycle: RemoteAccountLifecycleCommandWriter(
          client: client,
          invocationContext: (clientPageId) => invocationContext(
            AppUiSurfaces.settingsAccountSecurity,
            clientPageId,
            idempotencyKey: 'chat-api-cleanup-${session.ownerId}',
          ),
        ),
        session: session,
      );
    } catch (_) {
      httpClient.close();
      await telemetry.dispose();
      rethrow;
    }
  }

  final CloudHttpClient _httpClient;
  final ProductionCloudOperationTelemetryEvidence telemetry;
  final ChatRepository repository;
  final ChatMessageCommandWriter messageCommands;
  final ChatInboxQuery inbox;
  final ConversationUserStateCommandWriter userStateCommands;
  final MessageReceiptFactQuery receipts;
  final RemoteAccountLifecycleCommandWriter _accountLifecycle;
  final AuthSessionGrant session;

  Future<String> seedConversation({int maxGroupSize = 500}) async {
    final created = await repository.createConversation(
      type: 'group',
      title: 'L3 contract seed conversation',
      maxGroupSize: maxGroupSize,
      idempotencyKey: 'chat-contract-${DateTime.now().microsecondsSinceEpoch}',
    );
    if (created.conversationId.trim().isEmpty) {
      throw StateError('CreateConversation returned an empty conversationId');
    }
    return created.conversationId;
  }

  Future<ChatSendMessageResult> sendMessage(
    String conversationId,
    String clientMessageId,
  ) {
    return messageCommands.sendMessage(
      ChatSendMessageCommand(
        conversationId: conversationId,
        type: 'text',
        content: 'L3 contract test message',
        clientMsgId: clientMessageId,
        mentions: const <String>[],
      ),
    );
  }

  Future<void> close() async {
    try {
      await _accountLifecycle.closeAccount(
        CloseAccountCommand(
          clientRequestId: 'chat-api-cleanup-${session.ownerId}',
        ),
      );
      await telemetry.waitForEvents(minimumCount: 1);
    } finally {
      _httpClient.close();
      await telemetry.dispose();
    }
  }
}

final class _MutableAccessTokenProvider implements CloudAuthTokenProvider {
  String? accessToken;

  @override
  Future<String?> getAccessToken() async => accessToken;
}

final class _ChatApiClientContext implements CloudClientContextProvider {
  const _ChatApiClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'chat-api-contract',
      deviceActorId: chatApiContractDeviceId,
      platform: 'web',
      appVersion: 'api-integration',
      locale: 'zh-CN',
    );
  }
}
