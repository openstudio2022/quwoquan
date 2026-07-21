import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const bool kRunRemoteMediaPublicationUat = bool.fromEnvironment(
  'RUN_REMOTE_MEDIA_PUBLICATION_UAT',
);
const String _environment = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'gamma',
);
const String _gatewayBaseUrl = String.fromEnvironment(
  'API_CONTRACT_BASE_URL',
  defaultValue: 'https://gamma-api.quwoquan-env.test:19000',
);
const String _targetName = String.fromEnvironment(
  'REMOTE_MEDIA_UAT_TARGET',
  defaultValue: 'gamma-local',
);
const String _resolveHost = String.fromEnvironment(
  'REMOTE_MEDIA_UAT_RESOLVE_HOST',
  defaultValue: '127.0.0.1',
);

Future<void> runRemoteMediaPublicationUat(String scenario) async {
  expect(
    _gatewayBaseUrl.trim(),
    isNotEmpty,
    reason: 'Remote 媒体 UAT 必须显式连接真实网关。',
  );
  final arguments = <String>[
    'quwoquan_ops/tests/acceptance/user_acceptance/service_ops/'
        'content-service/smoke/run_media_publication_lifecycle_probe.py',
    '--env',
    _environment,
    '--target-name',
    _targetName,
    '--base-url',
    _gatewayBaseUrl,
    '--mode',
    'lifecycle',
    '--scenario',
    scenario,
    '--report',
    '.qwq_output/env/$_environment/runs/remote-media-uat/'
        '$scenario-media-publication.json',
  ];
  if (_resolveHost.trim().isNotEmpty) {
    arguments.addAll(<String>['--resolve-host', _resolveHost]);
  }

  final result = await Process.run(
    'python3',
    arguments,
    workingDirectory: '..',
  );
  final output = '${result.stdout}\n${result.stderr}';
  expect(result.exitCode, 0, reason: output);
}
