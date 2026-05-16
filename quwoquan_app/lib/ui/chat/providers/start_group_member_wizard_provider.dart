import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/ui/chat/models/start_group_pickable_member.dart';

class StartGroupMemberWizardState {
  const StartGroupMemberWizardState({
    this.selectedMembers = const <String, StartGroupPickableMember>{},
    this.lockedMemberIds = const <String>{},
    this.isBootstrapLoaded = false,
    this.isBootstrapLoading = false,
  });

  final Map<String, StartGroupPickableMember> selectedMembers;
  final Set<String> lockedMemberIds;
  final bool isBootstrapLoaded;
  final bool isBootstrapLoading;

  bool isLocked(String userId) => lockedMemberIds.contains(userId);

  bool isSelected(String userId) =>
      lockedMemberIds.contains(userId) || selectedMembers.containsKey(userId);

  StartGroupMemberWizardState copyWith({
    Map<String, StartGroupPickableMember>? selectedMembers,
    Set<String>? lockedMemberIds,
    bool? isBootstrapLoaded,
    bool? isBootstrapLoading,
  }) {
    return StartGroupMemberWizardState(
      selectedMembers: selectedMembers ?? this.selectedMembers,
      lockedMemberIds: lockedMemberIds ?? this.lockedMemberIds,
      isBootstrapLoaded: isBootstrapLoaded ?? this.isBootstrapLoaded,
      isBootstrapLoading: isBootstrapLoading ?? this.isBootstrapLoading,
    );
  }
}

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

final startGroupMemberWizardProvider =
    NotifierProvider.family<
      StartGroupMemberWizardController,
      StartGroupMemberWizardState,
      String
    >(StartGroupMemberWizardController.new);
