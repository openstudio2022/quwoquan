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
/// 所有治理写入均以 Remote 权威读回为成功边界。
class ConversationMembersNotifier extends Notifier<ConversationMembersState> {
  ConversationMembersNotifier(this._conversationId);

  final String _conversationId;
  int _loadGeneration = 0;

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
    Future<void>.microtask(() async {
      // 测试、route 或调用方可能在同一 event turn 显式请求加载；避免自动
      // load 随后启动并把已 await 的请求标记为 stale。
      if (_loadGeneration == 0) {
        await load();
      }
    });
    return ConversationMembersState(isLoading: true);
  }

  /// 加载成员列表和群组设置
  Future<bool> load() async {
    final generation = ++_loadGeneration;
    state = state.copyWith(isLoading: true, error: null);
    try {
      final results = await Future.wait([
        _memberRepo.listMembers(
          conversationId: _conversationId,
          limit: 200,
          sort: MemberListSort.joinedAsc,
        ),
        _adminRepo.getGroupSettings(_conversationId),
      ]);
      if (generation != _loadGeneration) return false;
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
      return true;
    } catch (e) {
      if (generation != _loadGeneration) return false;
      state = state.copyWith(
        isLoading: false,
        error: runtimeErrorDisplayMessage(e),
      );
      return false;
    }
  }

  /// 发送同一幂等意图，并以完整 Remote roster 读回作为唯一成功判定。
  Future<void> updateGroupAdmins(
    List<String> adminIds, {
    required String idempotencyKey,
  }) async {
    final expected = adminIds
        .map((id) => id.trim())
        .where((id) => id.isNotEmpty)
        .toSet();
    await _adminRepo.updateGroupAdmins(
      _conversationId,
      expected.toList(growable: false),
      idempotencyKey: idempotencyKey,
    );
    if (!await load()) {
      throw StateError('group admin authoritative readback failed');
    }
    final actual = state.members
        .where((member) => member.role == 'admin')
        .map((member) => member.userId)
        .toSet();
    if (!_sameIdentitySet(actual, expected)) {
      throw StateError('group admin authoritative readback did not converge');
    }
  }

  /// 转让仅在 Remote roster 读回恰好一个目标 owner 后成功。
  Future<void> transferOwnership(
    String newOwnerId, {
    required String idempotencyKey,
  }) async {
    final target = newOwnerId.trim();
    await _adminRepo.transferOwnership(
      _conversationId,
      target,
      idempotencyKey: idempotencyKey,
    );
    if (!await load()) {
      throw StateError('ownership authoritative readback failed');
    }
    final owners = state.members
        .where((member) => member.role == 'owner')
        .map((member) => member.userId)
        .toList(growable: false);
    if (owners.length != 1 || owners.single != target) {
      throw StateError('ownership authoritative readback did not converge');
    }
  }

  /// 更新群会话展示名（与会话资源对齐，不经群开关 PATCH）。
  Future<void> updateGroupDisplayTitle(String newTitle) async {
    await _conversationRepo.updateConversationTitle(_conversationId, newTitle);
  }

  /// 设置变更以 Remote Conversation 读回收敛为成功，不安装本地乐观真相。
  Future<void> updateGroupSettings(
    ChatGroupSettingsViewData next, {
    required String idempotencyKey,
  }) async {
    await _adminRepo.updateGroupSettings(
      _conversationId,
      next,
      idempotencyKey: idempotencyKey,
    );
    if (!await load()) {
      throw StateError('group settings authoritative readback failed');
    }
    if (state.groupSettings.nameEditableByAdminOnly !=
        next.nameEditableByAdminOnly) {
      throw StateError(
        'group settings authoritative readback did not converge',
      );
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
}

bool _sameIdentitySet(Set<String> left, Set<String> right) =>
    left.length == right.length && left.containsAll(right);

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
