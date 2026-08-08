import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_preference/application/assistant_preference_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

Future<List<AssistantPreference>> loadAssistantPreferences(
  AssistantPreferenceFacet facet,
) async {
  final results = await Future.wait(<Future<List<AssistantPreference>>>[
    facet.listAssistantPreferences(),
    facet.listAssistantPreferences(status: AssistantPreferenceStatus.revoked),
  ]);
  return List<AssistantPreference>.unmodifiable(<AssistantPreference>[
    ...results[0],
    ...results[1],
  ]);
}

/// 助理管理页显式偏好，统一走可撤销的 AssistantPreferenceFacet。
final assistantPreferencesProvider =
    FutureProvider.autoDispose<List<AssistantPreference>>((ref) async {
      final facet = ref.read(assistantPreferenceFacetProvider);
      return loadAssistantPreferences(facet);
    });
