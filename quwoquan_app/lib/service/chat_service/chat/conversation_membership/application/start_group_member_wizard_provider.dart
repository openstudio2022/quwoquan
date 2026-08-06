import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/start_group_pickable_member.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/start_group_member_wizard.dart';

class StartGroupMemberWizardController
    extends Notifier<StartGroupMemberWizardState> {
  StartGroupMemberWizardController(this.wizardId);

  final String wizardId;

  @override
  StartGroupMemberWizardState build() => const StartGroupMemberWizardState();

  void setBootstrapLoading() {
    state = state.copyWith(isBootstrapLoading: true, isBootstrapLoaded: false);
  }

  void completeBootstrap(Iterable<String> lockedMemberIds) {
    final normalizedLocked = lockedMemberIds
        .map((id) => id.trim())
        .where((id) => id.isNotEmpty)
        .toSet();
    final nextSelected = Map<String, StartGroupPickableMember>.from(
      state.selectedMembers,
    )..removeWhere((userId, _) => normalizedLocked.contains(userId));
    state = state.copyWith(
      selectedMembers: nextSelected,
      lockedMemberIds: normalizedLocked,
      isBootstrapLoaded: true,
      isBootstrapLoading: false,
    );
  }

  void toggleMember(StartGroupPickableMember member) {
    final userId = member.userId.trim();
    if (userId.isEmpty || state.lockedMemberIds.contains(userId)) {
      return;
    }
    final next = Map<String, StartGroupPickableMember>.from(
      state.selectedMembers,
    );
    if (next.containsKey(userId)) {
      next.remove(userId);
    } else {
      next[userId] = member;
    }
    state = state.copyWith(selectedMembers: next);
  }

  void selectMembers(Iterable<StartGroupPickableMember> members) {
    final next = Map<String, StartGroupPickableMember>.from(
      state.selectedMembers,
    );
    for (final member in members) {
      final userId = member.userId.trim();
      if (userId.isEmpty || state.lockedMemberIds.contains(userId)) {
        continue;
      }
      next[userId] = member;
    }
    state = state.copyWith(selectedMembers: next);
  }

  void deselectMemberIds(Iterable<String> userIds) {
    final next = Map<String, StartGroupPickableMember>.from(
      state.selectedMembers,
    );
    for (final userId in userIds.map((id) => id.trim())) {
      if (userId.isEmpty || state.lockedMemberIds.contains(userId)) {
        continue;
      }
      next.remove(userId);
    }
    state = state.copyWith(selectedMembers: next);
  }

  void clearSelectedMembers() {
    state = state.copyWith(
      selectedMembers: const <String, StartGroupPickableMember>{},
    );
  }
}
