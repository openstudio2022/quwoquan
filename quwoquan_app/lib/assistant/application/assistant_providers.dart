import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 助理「日程」tab 待办列表，统一走云端 AssistantPersonalDataFacet。
final assistantScheduleTasksProvider =
    FutureProvider.autoDispose<List<AssistantUserTaskView>>((ref) async {
      return ref
          .read(assistantPersonalDataFacetProvider)
          .listAssistantTasks(limit: 32);
    });

/// 助理管理页显式偏好事实，统一走可撤销的 AssistantPreferenceFactFacet。
final assistantPreferencesProvider =
    FutureProvider.autoDispose<List<AssistantPreferenceFact>>((ref) async {
      return ref
          .read(assistantPreferenceFactFacetProvider)
          .listAssistantPreferences();
    });
