import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_cloud_contracts/generated/chat_contracts.dart';

/// Immutable presentation state for the canonical conversation membership UI.
class ConversationMembersState {
  ConversationMembersState({
    this.members = const [],
    ChatGroupSettingsViewData? groupSettings,
    this.isLoading = false,
    this.error,
  }) : groupSettings = groupSettings ?? _defaultGroupSettings;

  static final ChatGroupSettingsViewData _defaultGroupSettings =
      ChatGroupSettingsViewData(
        nameEditableByAdminOnly: false,
        conversationType: 'group',
      );

  final List<ConversationMemberListRow> members;
  final ChatGroupSettingsViewData groupSettings;
  final bool isLoading;
  final String? error;

  String get currentUserRole {
    for (final member in members) {
      if (member.isCurrentUser) return member.role;
    }
    return 'member';
  }

  bool get isAdminOrOwner =>
      currentUserRole == 'owner' || currentUserRole == 'admin';

  bool get isOwner => currentUserRole == 'owner';

  ConversationMembersState copyWith({
    List<ConversationMemberListRow>? members,
    ChatGroupSettingsViewData? groupSettings,
    bool? isLoading,
    String? error,
  }) {
    return ConversationMembersState(
      members: members ?? this.members,
      groupSettings: groupSettings ?? this.groupSettings,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}
