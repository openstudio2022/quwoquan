import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/adapters/flutter_assistant_run_policy_text_source.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_run_policy_loader.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart'
    show fileStorageGatewayProvider;

const String _assistantRunProgressTextPolicyPath =
    'assets/assistant/config/progress_text_policy.json';

final assistantRunPolicyLoaderProvider = Provider<AssistantRunPolicyLoader>(
  (ref) => AssistantRunPolicyLoader(
    source: FlutterAssistantRunPolicyTextSource(
      assetBundle: rootBundle,
      fileStorageGateway: ref.watch(fileStorageGatewayProvider),
    ),
    path: _assistantRunProgressTextPolicyPath,
  ),
);
