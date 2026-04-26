import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_conversation_member_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_group_settings_dto.g.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';

/// 会话成员及设置的共享状态
class ConversationMembersState {
  final List<ChatConversationMemberDto> members;
  final ChatGroupSettingsDto groupSettings;
  final bool isLoading;
  final String? error;

  static final ChatGroupSettingsDto _defaultGroupSettings =
      ChatGroupSettingsDto(
        qrCodeJoinEnabled: true,
        joinRequiresApproval: false,
        nameEditableByAdminOnly: false,
        privacyShieldAdminOnly: false,
        conversationType: 'group',
      );

  ConversationMembersState({
    this.members = const [],
    ChatGroupSettingsDto? groupSettings,
    this.isLoading = false,
    this.error,
  }) : groupSettings = groupSettings ?? _defaultGroupSettings;

  /// 当前登录用户的角色（'owner' | 'admin' | 'member'）
  String get currentUserRole {
    for (final m in members) {
      if (m.isCurrentUser) {
        return m.role;
      }
    }
    return 'member';
  }

  bool get isAdminOrOwner =>
      currentUserRole == 'owner' || currentUserRole == 'admin';

  bool get isOwner => currentUserRole == 'owner';

  ConversationMembersState copyWith({
    List<ChatConversationMemberDto>? members,
    ChatGroupSettingsDto? groupSettings,
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

/// 会话成员及设置的 Notifier（family by conversationId）
/// 提供乐观更新写操作，失败时自动回滚
class ConversationMembersNotifier extends Notifier<ConversationMembersState> {
  ConversationMembersNotifier(this._conversationId);

  final String _conversationId;
  int _pendingWrites = 0;

  ChatRepository get _repo => ref.read(chatRepositoryProvider);
  String get _currentUserId => ref.read(currentUserIdProvider);

  @override
  ConversationMembersState build() {
    ref.watch(chatRepositoryProvider);
    ref.watch(currentUserIdProvider);
    Future<void>.microtask(load);
    return ConversationMembersState(isLoading: true);
  }

  /// 加载成员列表和群组设置
  Future<void> load() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final results = await Future.wait([
        _repo.listMembers(
          conversationId: _conversationId,
          limit: 200,
          sort: 'joined_asc',
        ),
        _repo.getGroupSettings(_conversationId),
      ]);
      // 若有乐观写操作进行中，跳过覆盖，避免竞态
      if (_pendingWrites > 0) return;
      final raw = results[0] as List<ChatConversationMemberDto>;
      final members = raw
          .map(
            (member) =>
                member.copyWith(isCurrentUser: member.userId == _currentUserId),
          )
          .toList(growable: false);
      state = state.copyWith(
        members: members,
        groupSettings: results[1] as ChatGroupSettingsDto,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        error: runtimeErrorDisplayMessage(e),
      );
    }
  }

  /// 乐观更新管理员列表；失败时回滚
  Future<void> updateGroupAdmins(List<String> adminIds) async {
    final previous = state;
    _pendingWrites++;
    state = state.copyWith(members: _applyAdminChange(state.members, adminIds));
    try {
      await _repo.updateGroupAdmins(_conversationId, adminIds);
    } catch (e) {
      state = previous;
      rethrow;
    } finally {
      _pendingWrites--;
    }
  }

  /// 乐观更新群主转让；失败时回滚
  Future<void> transferOwnership(String newOwnerId) async {
    final previous = state;
    _pendingWrites++;
    state = state.copyWith(
      members: _applyOwnerTransfer(state.members, newOwnerId),
    );
    try {
      await _repo.transferOwnership(_conversationId, newOwnerId);
    } catch (e) {
      state = previous;
      rethrow;
    } finally {
      _pendingWrites--;
    }
  }

  /// 更新群会话展示名（与会话资源对齐，不经群开关 PATCH）。
  Future<void> updateGroupDisplayTitle(String newTitle) async {
    await _repo.updateConversationTitle(_conversationId, newTitle);
  }

  /// 乐观更新群组设置；失败时回滚
  Future<void> updateGroupSettings(ChatGroupSettingsDto next) async {
    final previous = state;
    state = state.copyWith(groupSettings: next);
    try {
      await _repo.updateGroupSettings(_conversationId, next);
    } catch (e) {
      state = previous;
      rethrow;
    }
  }

  static List<ChatConversationMemberDto> _applyAdminChange(
    List<ChatConversationMemberDto> members,
    List<String> adminIds,
  ) {
    return members.map((m) {
      if (m.role == 'owner') return m;
      return m.copyWith(role: adminIds.contains(m.userId) ? 'admin' : 'member');
    }).toList();
  }

  static List<ChatConversationMemberDto> _applyOwnerTransfer(
    List<ChatConversationMemberDto> members,
    String newOwnerId,
  ) {
    return members.map((m) {
      if (m.isCurrentUser) {
        return m.copyWith(role: 'member');
      }
      if (m.userId == newOwnerId) {
        return m.copyWith(role: 'owner');
      }
      return m;
    }).toList();
  }
}

/// 会话成员与设置的全局共享 Provider（family by conversationId）
final conversationMembersProvider =
    NotifierProvider.family<
      ConversationMembersNotifier,
      ConversationMembersState,
      String
    >(ConversationMembersNotifier.new);
