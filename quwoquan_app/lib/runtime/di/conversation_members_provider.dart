import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/chat_conversation_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation/application/public/chat_conversation_view_data.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/application/public/chat_member_repository.dart';
import 'package:quwoquan_app/service/chat_service/chat/conversation_membership/presentation/conversation_members_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/transport/media/avatar_image_url.dart';

/// 会话成员及设置的 Notifier（family by conversationId）
/// 提供乐观更新写操作，失败时自动回滚
class ConversationMembersNotifier extends Notifier<ConversationMembersState> {
  ConversationMembersNotifier(this._conversationId);

  final String _conversationId;
  int _pendingWrites = 0;

  ChatMemberRepository get _memberRepo =>
      ref.read(chatMemberRepositoryProvider);
  ChatGroupAdminRepository get _adminRepo =>
      ref.read(chatGroupAdminRepositoryProvider);
  ChatConversationRepository get _conversationRepo =>
      ref.read(chatConversationRepositoryProvider);
  String get _currentUserId => ref.read(currentUserIdProvider);

  @override
  ConversationMembersState build() {
    ref.watch(chatMemberRepositoryProvider);
    ref.watch(currentUserIdProvider);
    Future<void>.microtask(load);
    return ConversationMembersState(isLoading: true);
  }

  /// 加载成员列表和群组设置
  Future<void> load() async {
    state = state.copyWith(isLoading: true, error: null);
    try {
      final results = await Future.wait([
        _memberRepo.listMembers(
          conversationId: _conversationId,
          limit: 200,
          sort: 'joined_asc',
        ),
        _adminRepo.getGroupSettings(_conversationId),
      ]);
      // 若有乐观写操作进行中，跳过覆盖，避免竞态
      if (_pendingWrites > 0) return;
      final raw = results[0] as List<ConversationMemberListRow>;
      final members = raw
          .map(
            (member) => _copyMember(
              member,
              avatarUrl: resolveAvatarImageUrl(member.avatarUrl),
              isCurrentUser: member.userId == _currentUserId,
            ),
          )
          .toList(growable: false);
      state = state.copyWith(
        members: members,
        groupSettings: results[1] as ChatGroupSettingsViewData,
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
      await _adminRepo.updateGroupAdmins(_conversationId, adminIds);
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
      await _adminRepo.transferOwnership(_conversationId, newOwnerId);
    } catch (e) {
      state = previous;
      rethrow;
    } finally {
      _pendingWrites--;
    }
  }

  /// 更新群会话展示名（与会话资源对齐，不经群开关 PATCH）。
  Future<void> updateGroupDisplayTitle(String newTitle) async {
    await _conversationRepo.updateConversationTitle(_conversationId, newTitle);
  }

  /// 乐观更新群组设置；失败时回滚
  Future<void> updateGroupSettings(ChatGroupSettingsViewData next) async {
    final previous = state;
    state = state.copyWith(groupSettings: next);
    try {
      await _adminRepo.updateGroupSettings(_conversationId, next);
    } catch (e) {
      state = previous;
      rethrow;
    }
  }

  /// 添加成员后从云端刷新 roster。
  Future<void> addMembers(List<String> userIds) async {
    await _memberRepo.addMembers(
      conversationId: _conversationId,
      userIds: userIds,
    );
    await load();
  }

  /// 移出成员（群治理动作，仅 owner/admin）后从云端刷新 roster。
  Future<void> removeMember(String userId) async {
    await _memberRepo.removeMember(
      conversationId: _conversationId,
      userId: userId,
    );
    await load();
  }

  /// 主动退出群聊（自愿离开语义；owner 须先转让）。
  Future<void> leaveConversation() async {
    await _memberRepo.leaveConversation(_conversationId);
  }

  /// 更新群公告（owner/admin；发布即触达）。
  Future<void> updateAnnouncement(String announcement) async {
    await _adminRepo.updateAnnouncement(_conversationId, announcement);
  }

  static List<ConversationMemberListRow> _applyAdminChange(
    List<ConversationMemberListRow> members,
    List<String> adminIds,
  ) {
    return members.map((m) {
      if (m.role == 'owner') return m;
      return _copyMember(
        m,
        role: adminIds.contains(m.userId) ? 'admin' : 'member',
      );
    }).toList();
  }

  static List<ConversationMemberListRow> _applyOwnerTransfer(
    List<ConversationMemberListRow> members,
    String newOwnerId,
  ) {
    return members.map((m) {
      if (m.isCurrentUser) {
        return _copyMember(m, role: 'member');
      }
      if (m.userId == newOwnerId) {
        return _copyMember(m, role: 'owner');
      }
      return m;
    }).toList();
  }
}

ConversationMemberListRow _copyMember(
  ConversationMemberListRow source, {
  String? avatarUrl,
  String? role,
  bool? isCurrentUser,
}) {
  return ConversationMemberListRow(
    userId: source.userId,
    userHandle: source.userHandle,
    displayName: source.displayName,
    avatarUrl: avatarUrl ?? source.avatarUrl,
    role: role ?? source.role,
    memberType: source.memberType,
    joinedAt: source.joinedAt,
    isCurrentUser: isCurrentUser ?? source.isCurrentUser,
  );
}

/// 会话成员与设置的全局共享 Provider（family by conversationId）
final conversationMembersProvider =
    NotifierProvider.family<
      ConversationMembersNotifier,
      ConversationMembersState,
      String
    >(ConversationMembersNotifier.new);
