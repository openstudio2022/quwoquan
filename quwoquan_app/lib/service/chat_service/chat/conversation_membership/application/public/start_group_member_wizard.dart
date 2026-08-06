import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/start_group_pickable_member.dart';

final class StartGroupMemberWizardState {
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
