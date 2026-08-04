import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/contact_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_membership_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/conversation_user_state_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/conversation/message_home_remote.dart';
import 'package:quwoquan_app/cloud/remote/chat/message/message_remote.dart';
import 'package:quwoquan_app/cloud/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/chat/remote/chat_repository_remote.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/recording_cloud_operation_telemetry_sink.dart';

const _runSmoke = bool.fromEnvironment('RUN_LOCAL_GAMMA_REMOTE_SMOKE');
const _baseUrl = String.fromEnvironment(
  'LOCAL_GAMMA_CHAT_BASE_URL',
  defaultValue: 'http://127.0.0.1:19200',
);
const _mongoPort = String.fromEnvironment(
  'LOCAL_GAMMA_MONGO_PORT',
  defaultValue: '19410',
);
const _viewerId = String.fromEnvironment(
  'APP_CURRENT_USER_ID',
  defaultValue: 'fixture_user_current',
);
final _acceptanceToken =
    Platform.environment['LOCAL_GAMMA_ACCEPTANCE_TOKEN'] ?? '';
const _photoGroupId = 'fixture_conv_photo_group';

final class _AcceptanceTokenProvider implements CloudAuthTokenProvider {
  const _AcceptanceTokenProvider(this.token);

  final String token;

  @override
  Future<String?> getAccessToken() async => token.trim().isEmpty ? null : token;
}

Future<void> _ensureChatFixtureSeeded() async {
  final chatServiceDir = Directory(
    '${Directory.current.path}/../quwoquan_service/services/chat-service',
  );
  if (!chatServiceDir.existsSync()) {
    return;
  }
  final result = await Process.run('go', <String>[
    'run',
    './cmd/seed-fixture',
    '--mongo-uri',
    'mongodb://127.0.0.1:$_mongoPort/?directConnection=true',
    '--database',
    'quwoquan_chat',
    '--seed-ref',
    'chat_core',
    '--seed-ref',
    'chat_contacts_core',
  ], workingDirectory: chatServiceDir.path);
  expect(result.exitCode, 0, reason: '${result.stdout}\n${result.stderr}');
}

Future<GroupHome> _loadGroupHome(RemoteChatRepository repo) async {
  try {
    return await repo.getGroupHome(_photoGroupId);
  } on Object {
    await _ensureChatFixtureSeeded();
    return repo.getGroupHome(_photoGroupId);
  }
}

void main() {
  test(
    'RemoteChatRepository group home memberCount matches listMembers roster',
    () async {
      if (!_runSmoke) {
        return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
      }
      expect(
        _acceptanceToken,
        isNotEmpty,
        reason: 'LOCAL_GAMMA_ACCEPTANCE_TOKEN is required for remote smoke.',
      );

      final telemetry = RecordingCloudOperationTelemetrySink();
      final client = buildGeneratedCloudOperationClient(
        httpClient: CloudHttpClient(
          authTokenProvider: _AcceptanceTokenProvider(_acceptanceToken),
        ),
        clientContextProvider: const _GammaClientContextProvider(),
        telemetrySink: telemetry,
        environment: CloudRuntimeEnvironment(
          environment: CloudEnvironment.gamma,
          gatewayBaseUri: Uri.parse(_baseUrl),
        ),
      );
      CloudOperationInvocationContext context(
        AppUiSurface surface,
        String clientPageId, {
        String? idempotencyKey,
      }) {
        return CloudOperationInvocationContext(
          surfaceId: surface.id,
          routeId: surface.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(
            accountId: _viewerId,
            personaId: _viewerId,
          ),
          idempotencyKey: idempotencyKey,
        );
      }

      final conversationQuery = RemoteChatConversationQuery(
        client: client,
        invocationContext: (clientPageId) =>
            context(AppUiSurfaces.chatAnnouncement, clientPageId),
      );
      final contactQuery = RemoteChatContactQuery(
        client: client,
        invocationContext: (clientPageId) =>
            context(AppUiSurfaces.chatList, clientPageId),
      );
      final membershipQuery = RemoteChatConversationMembershipQuery(
        client: client,
        invocationContext: (clientPageId) =>
            context(AppUiSurfaces.chatManage, clientPageId),
      );
      final repo = RemoteChatRepository(
        conversationQuery: conversationQuery,
        conversationCommandWriter: RemoteChatConversationCommandWriter(
          client: client,
          invocationContext: (clientPageId, idempotencyKey) => context(
            AppUiSurfaces.chatManage,
            clientPageId,
            idempotencyKey: idempotencyKey,
          ),
        ),
        contactQuery: contactQuery,
        inboxQuery: contactQuery,
        messageHomeQuery: RemoteChatMessageHomeQuery(
          client: client,
          invocationContext: (clientPageId) =>
              context(AppUiSurfaces.chatList, clientPageId),
        ),
        membershipQuery: membershipQuery,
        membershipCommandWriter: RemoteChatConversationMembershipCommandWriter(
          client: client,
          invocationContext: (clientPageId, idempotencyKey) => context(
            AppUiSurfaces.chatSettings,
            clientPageId,
            idempotencyKey: idempotencyKey,
          ),
        ),
        userStateCommandWriter: RemoteChatConversationUserStateCommandWriter(
          client: client,
          invocationContext: (clientPageId, idempotencyKey) => context(
            AppUiSurfaces.chatDetail,
            clientPageId,
            idempotencyKey: idempotencyKey,
          ),
        ),
        messageQuery: RemoteChatMessageQuery(
          client: client,
          invocationContext: (clientPageId) =>
              context(AppUiSurfaces.chatDetail, clientPageId),
        ),
        messageMutationWriter: RemoteChatMessageMutationWriter(
          client: client,
          invocationContext: (clientPageId, idempotencyKey) => context(
            AppUiSurfaces.chatDetail,
            clientPageId,
            idempotencyKey: idempotencyKey,
          ),
        ),
      );

      final home = await _loadGroupHome(repo);
      expect(home.conversationId, _photoGroupId);
      expect(home.memberCount, 3);
      expect(home.avatarUrl, isNotEmpty);

      final members = await repo.listMembers(
        conversationId: _photoGroupId,
        limit: 50,
      );
      expect(members.length, home.memberCount);
      expect(
        members.map((member) => member.userId).toSet().length,
        members.length,
      );
      expect(telemetry.events, isNotEmpty);
      expect(telemetry.events.every((event) => event.succeeded), isTrue);
    },
  );
}

final class _GammaClientContextProvider implements CloudClientContextProvider {
  const _GammaClientContextProvider();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'chat-group-roster-parity',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}
