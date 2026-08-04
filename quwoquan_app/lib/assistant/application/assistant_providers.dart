import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 助理「日程」tab 待办列表，统一走云端 AssistantPersonalDataFacet。
final assistantScheduleTasksProvider =
    FutureProvider.autoDispose<List<AssistantTaskItemView>>((ref) async {
      return ref
          .read(assistantPersonalDataFacetProvider)
          .listAssistantTasks(limit: 32);
    });

/// 助理管理页显式偏好，统一走可撤销的 AssistantPreferenceFacet。
final assistantPreferencesProvider =
    FutureProvider.autoDispose<List<AssistantPreference>>((ref) async {
      final facet = ref.read(assistantPreferenceFacetProvider);
      final results = await Future.wait(<Future<List<AssistantPreference>>>[
        facet.listAssistantPreferences(),
        facet.listAssistantPreferences(
          status: AssistantPreferenceStatus.revoked,
        ),
      ]);
      return <AssistantPreference>[...results[0], ...results[1]];
    });
