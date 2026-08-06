import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/contact_candidate_vm.dart';

/// 「添加」按钮态由关系能力位驱动，UI 不自枚举 relationState（与 follow 语义对齐）。
void main() {
  ContactAddState resolve({
    required String relationState,
    bool canFollow = true,
    bool canUnfollow = false,
  }) => ContactCandidateVm.addStateFromCapability(
    relationState: relationState,
    canFollow: canFollow,
    canUnfollow: canUnfollow,
  );

  group('addStateFromCapability', () {
    test('self → 不展示添加动作', () {
      expect(resolve(relationState: 'self'), ContactAddState.isSelf);
    });

    test('following / mutual → 已添加', () {
      expect(resolve(relationState: 'following'), ContactAddState.added);
      expect(resolve(relationState: 'mutual'), ContactAddState.added);
    });

    test('followed_by → 回关', () {
      expect(resolve(relationState: 'followed_by'), ContactAddState.canFollowBack);
    });

    test('not_following → 可添加', () {
      expect(resolve(relationState: 'not_following'), ContactAddState.canAdd);
    });

    test('关系态缺省时回退能力位：仅 canUnfollow 视为已添加', () {
      expect(
        resolve(relationState: '', canFollow: false, canUnfollow: true),
        ContactAddState.added,
      );
      expect(
        resolve(relationState: 'unknown', canFollow: true, canUnfollow: false),
        ContactAddState.canAdd,
      );
    });
  });

  group('ContactAddStateX.canTriggerAdd', () {
    test('canAdd / canFollowBack 可触发添加；added / isSelf 不可', () {
      expect(ContactAddState.canAdd.canTriggerAdd, isTrue);
      expect(ContactAddState.canFollowBack.canTriggerAdd, isTrue);
      expect(ContactAddState.added.canTriggerAdd, isFalse);
      expect(ContactAddState.isSelf.canTriggerAdd, isFalse);
    });
  });
}
