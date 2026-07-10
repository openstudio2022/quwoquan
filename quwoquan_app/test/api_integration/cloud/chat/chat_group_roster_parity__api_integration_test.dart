import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/group_home_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/remote/chat_repository_remote.dart';

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
const _photoGroupId = 'fixture_conv_photo_group';

Future<Map<String, String>> _gammaHeaders(Map<String, String> base) async {
  return CloudRequestHeaders.withOwnerSubAccountContext(
    base,
    ownerUserId: _viewerId,
  );
}

Future<void> _ensureChatFixtureSeeded() async {
  final chatServiceDir = Directory(
    '${Directory.current.path}/../quwoquan_service/services/chat-service',
  );
  if (!chatServiceDir.existsSync()) {
    return;
  }
  final result = await Process.run(
    'go',
    <String>[
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
    ],
    workingDirectory: chatServiceDir.path,
  );
  expect(
    result.exitCode,
    0,
    reason: '${result.stdout}\n${result.stderr}',
  );
}

Future<GroupHomeDto> _loadGroupHome(RemoteChatRepository repo) async {
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

      final repo = RemoteChatRepository(
        baseUrl: _baseUrl,
        mergeRequestContext: _gammaHeaders,
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
    },
  );
}
