import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/assistant_history_loader.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_session/application/public/assistant_history.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show assistantSessionRunFacetProvider;

final assistantHistoryLoaderProvider = Provider<AssistantHistoryLoader>(
  (ref) =>
      CloudAssistantHistoryLoader(ref.watch(assistantSessionRunFacetProvider)),
);
