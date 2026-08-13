// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/shared-surface-skill-placement/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/spec.md#req-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_surface_placement/domain/skill_surface_placement_disabled_skills.dart';

void main() {
  group('normalizeForSubmit', () {
    test('丢弃 active package 目录外的 skillId', () {
      final normalized = SkillSurfacePlacementDisabledSkills.normalizeForSubmit(
        edited: <String>{'skill.b', 'skill.retired', 'skill.a'},
        activeSkillIds: <String>{'skill.a', 'skill.b'},
      );

      expect(normalized, <String>['skill.a', 'skill.b']);
    });

    test('去重并稳定排序', () {
      final normalized = SkillSurfacePlacementDisabledSkills.normalizeForSubmit(
        edited: <String>['skill.c', 'skill.a', 'skill.c'],
        activeSkillIds: <String>{'skill.a', 'skill.c'},
      );

      expect(normalized, <String>['skill.a', 'skill.c']);
    });

    test('目录为空时提交空集合', () {
      final normalized = SkillSurfacePlacementDisabledSkills.normalizeForSubmit(
        edited: <String>{'skill.a'},
        activeSkillIds: const <String>{},
      );

      expect(normalized, isEmpty);
    });

    test('返回不可变列表，调用方不能就地改写待提交形状', () {
      final normalized = SkillSurfacePlacementDisabledSkills.normalizeForSubmit(
        edited: <String>{'skill.a'},
        activeSkillIds: <String>{'skill.a'},
      );

      expect(() => normalized.add('skill.b'), throwsUnsupportedError);
    });
  });

  group('toggle', () {
    test('enabled 为真时移出禁用集合', () {
      final next = SkillSurfacePlacementDisabledSkills.toggle(
        disabled: <String>{'skill.a', 'skill.b'},
        skillId: 'skill.a',
        enabled: true,
      );

      expect(next, <String>{'skill.b'});
    });

    test('enabled 为假时加入禁用集合', () {
      final next = SkillSurfacePlacementDisabledSkills.toggle(
        disabled: <String>{'skill.a'},
        skillId: 'skill.b',
        enabled: false,
      );

      expect(next, <String>{'skill.a', 'skill.b'});
    });

    test('不修改传入集合', () {
      final original = <String>{'skill.a'};

      SkillSurfacePlacementDisabledSkills.toggle(
        disabled: original,
        skillId: 'skill.b',
        enabled: false,
      );

      expect(original, <String>{'skill.a'});
    });
  });

  test('isDisabled 按 placement 事实判定', () {
    expect(
      SkillSurfacePlacementDisabledSkills.isDisabled(
        disabledSkillIds: const <String>['skill.a'],
        skillId: 'skill.a',
      ),
      isTrue,
    );
    expect(
      SkillSurfacePlacementDisabledSkills.isDisabled(
        disabledSkillIds: const <String>['skill.a'],
        skillId: 'skill.b',
      ),
      isFalse,
    );
  });
}
