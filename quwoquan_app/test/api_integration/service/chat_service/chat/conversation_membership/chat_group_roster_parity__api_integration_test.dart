import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/auth/cloud_auth_token_provider.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/di/chat_dependencies.dart';
import 'package:quwoquan_app/runtime/di/chat_repository_facade.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/production_cloud_operation_telemetry_evidence.dart';

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

Future<GroupHome> _loadGroupHome(ChatRepository repo) async {
  try {
    return await repo.getGroupHome(_photoGroupId);
  } on Object {
    await _ensureChatFixtureSeeded();
    return repo.getGroupHome(_photoGroupId);
  }
}

void main() {
  test(
    'production chat composition group home matches member roster',
    () async {
      if (!_runSmoke) {
        return markTestSkipped('Set RUN_LOCAL_GAMMA_REMOTE_SMOKE=true.');
      }
      expect(
        _acceptanceToken,
        isNotEmpty,
        reason: 'LOCAL_GAMMA_ACCEPTANCE_TOKEN is required for remote smoke.',
      );

      final telemetry = await ProductionCloudOperationTelemetryEvidence.start(
        clientContextProvider: const _GammaClientContextProvider(),
      );
      addTearDown(telemetry.dispose);
      final client = buildGeneratedCloudOperationClient(
        httpClient: CloudHttpClient(
          authTokenProvider: _AcceptanceTokenProvider(_acceptanceToken),
        ),
        clientContextProvider: const _GammaClientContextProvider(),
        telemetrySink: telemetry.sink,
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

      final repo = ChatProductionComposition.repository(
        client: client,
        invocationContext: context,
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
      final telemetryEvents = await telemetry.waitForEvents(minimumCount: 1);
      expect(telemetryEvents, isNotEmpty);
      expect(telemetryEvents.every((event) => event.succeeded), isTrue);
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
