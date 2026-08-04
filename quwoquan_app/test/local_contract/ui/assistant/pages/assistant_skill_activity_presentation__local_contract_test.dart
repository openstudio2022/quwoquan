// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_activity_presentation.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('every canonical Skill Activity semantic has a user label', () {
    for (final key in SkillActivityDisplayKey.values) {
      expect(
        assistantSkillActivityLabel(key).trim(),
        isNotEmpty,
        reason: key.wireName,
      );
    }
    for (final action in SkillDataControlAction.values) {
      expect(
        assistantSkillDataControlActionLabel(action).trim(),
        isNotEmpty,
        reason: action.wireName,
      );
    }
    for (final status in SkillDataControlRequestStatus.values) {
      expect(
        assistantSkillDataControlStatusLabel(status).trim(),
        isNotEmpty,
        reason: status.wireName,
      );
    }
  });
}
