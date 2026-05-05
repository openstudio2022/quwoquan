import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 助理「日程」tab 待办列表，统一走云端 AssistantRepository。
final assistantScheduleTasksProvider =
    FutureProvider.autoDispose<List<AssistantUserTaskView>>((ref) async {
      return ref.read(assistantRepositoryProvider).listAssistantTasks(limit: 32);
    });
