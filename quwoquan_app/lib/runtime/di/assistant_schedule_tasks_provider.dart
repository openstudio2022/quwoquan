import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 助理「日程」tab 待办列表，统一走 AssistantTaskView query。
final assistantScheduleTasksProvider =
    FutureProvider.autoDispose<List<AssistantTaskItemView>>((ref) async {
      return ref.read(assistantTaskQueryProvider).listAssistantTasks(limit: 32);
    });
