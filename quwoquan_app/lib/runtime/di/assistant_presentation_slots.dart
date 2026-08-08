import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show
        assistantSkillActivityQueryProvider,
        skillDataControlProcessCommandWriterProvider,
        skillDataControlProcessQueryProvider;
import 'package:quwoquan_app/service/assistant_service/assistant/skill_data_control_request/presentation/assistant_skill_lifecycle_sheet.dart';

/// Composition-root slot used by the Skill Catalog without importing another
/// object's private presentation library.
typedef AssistantSkillLifecyclePresenter =
    Future<void> Function({
      required BuildContext context,
      required String skillId,
      required String skillName,
      required void Function(String action) onProductAction,
    });

final assistantSkillLifecyclePresenterProvider =
    Provider<AssistantSkillLifecyclePresenter>((ref) {
      return ({
        required context,
        required skillId,
        required skillName,
        required onProductAction,
      }) {
        return showAssistantSkillLifecycleSheet(
          context: context,
          skillId: skillId,
          skillName: skillName,
          activityQuery: ref.read(assistantSkillActivityQueryProvider),
          dataControlCommandWriter: ref.read(
            skillDataControlProcessCommandWriterProvider,
          ),
          dataControlQuery: ref.read(skillDataControlProcessQueryProvider),
          onProductAction: (action) => onProductAction(action.name),
        );
      };
    });
