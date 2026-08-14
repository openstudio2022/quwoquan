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
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/adapters/media_asset_remote.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/content_media_object_uploader.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/adapters/media_upload_session_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/adapters/conversation_user_state_remote.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/application/public/conversation_user_state_command_writer.dart';
import 'package:quwoquan_app/service/chat_service/chat/message_receipt_fact/application/public/message_receipt_fact_query.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'api_contract_environment.dart';
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
    required this.mediaUploads,
    required this.mediaAssets,
    required this._accountLifecycle,
    required this.session,
  });

  static Future<ChatApiContractHarness> create() async {
    ApiContractEnvironment.ensureLocalTlsRootTrusted();
    if (_apiBase.isEmpty) {
      throw StateError(
        'L3: API_CONTRACT_BASE_URL was not injected by the canonical '
        'stackctl App API integration launcher',
      );
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
        mediaUploads: RemoteContentMediaUploadSessionAdapter(
          client: client,
          invocationContext: (clientPageId, {required bool command}) =>
              invocationContext(AppUiSurfaces.chatDetail, clientPageId),
        ),
        mediaAssets: RemoteContentMediaAssetAdapter(
          client: client,
          invocationContext: (clientPageId, {required bool command}) =>
              invocationContext(AppUiSurfaces.chatDetail, clientPageId),
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
  final RemoteContentMediaUploadSessionAdapter mediaUploads;
  final RemoteContentMediaAssetAdapter mediaAssets;
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

  /// 经生产上传链（init -> data-plane PUT -> complete -> ready 轮询）产出
  /// owner-scoped ready 的 audio MediaAsset，返回 assetId。
  Future<String> uploadReadyAudioAsset() async {
    final bytes = Uint8List.fromList(
      utf8.encode(
        'quwoquan-audio-l3-${DateTime.now().microsecondsSinceEpoch}',
      ),
    );
    final sha = sha256.convert(bytes).toString();
    final init = await mediaUploads.initUpload(
      InitContentMediaUploadCommand(
        mediaType: MediaType.audio,
        mimeType: 'audio/mp4',
        fileSize: bytes.length,
        expectedSha256: sha,
      ),
      ContentMediaUploadCommandContext(
        idempotencyKey:
            'chat-audio-init-${DateTime.now().microsecondsSinceEpoch}',
      ),
    );
    final uploadUrl = init.uploadUrl;
    if (uploadUrl == null) {
      throw StateError('InitMediaUpload returned no uploadUrl');
    }

    final dataPlaneClient = CloudHttpClient(authTokenProvider: null);
    try {
      final uploader = RemoteContentMediaObjectUploader(
        client: dataPlaneClient,
        uploadBaseUrl: uploadUrl.replace(path: '/', query: '').toString(),
      );
      await uploader.stream(
        uploadUrl,
        Stream<List<int>>.value(bytes),
        contentLength: bytes.length,
        mimeType: 'audio/mp4',
        expectedSha256: sha,
      );
    } finally {
      dataPlaneClient.close();
    }

    final completed = await mediaUploads.completeUpload(
      CompleteContentMediaUploadCommand(sessionId: init.sessionId),
      ContentMediaUploadCommandContext(
        idempotencyKey: 'chat-audio-complete-${init.sessionId}',
      ),
    );
    var assetId = completed.assetId?.trim() ?? '';
    if (assetId.isEmpty) {
      final session = await mediaUploads.getUploadSession(
        GetContentMediaUploadSessionQuery(sessionId: init.sessionId),
      );
      assetId = session.assetId?.trim() ?? '';
    }
    if (assetId.isEmpty) {
      throw StateError('CompleteMediaUpload produced no MediaAsset');
    }

    var processing = completed.assetProcessingStatus;
    final deadline = DateTime.now().add(const Duration(seconds: 30));
    while (processing != MediaAssetStatus.ready &&
        DateTime.now().isBefore(deadline)) {
      await Future<void>.delayed(const Duration(milliseconds: 500));
      final asset = await mediaAssets.getMediaAsset(
        GetContentMediaAssetQuery(mediaId: assetId),
      );
      processing = asset.status;
    }
    if (processing != MediaAssetStatus.ready) {
      throw StateError('audio MediaAsset did not become ready in budget');
    }
    return assetId;
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
