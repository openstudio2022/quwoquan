import 'package:flutter_riverpod/legacy.dart';
import 'package:quwoquan_app/cloud/services/chat/chat_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

/// 会话成员及设置的共享状态
class ConversationMembersState {
  final List<Map<String, dynamic>> members;
  final Map<String, dynamic> settings;
  final bool isLoading;
  final String? error;

  const ConversationMembersState({
    this.members = const [],
    this.settings = const {},
    this.isLoading = false,
    this.error,
  });

  /// 当前登录用户的角色（'owner' | 'admin' | 'member'）
  String get currentUserRole {
    try {
      final m = members.firstWhere(
        (m) => m['isCurrentUser'] == true,
        orElse: () => const {},
      );
      return m['role'] as String? ?? 'member';
    } catch (_) {
      return 'member';
    }
  }

  bool get isAdminOrOwner =>
      currentUserRole == 'owner' || currentUserRole == 'admin';

  bool get isOwner => currentUserRole == 'owner';

  ConversationMembersState copyWith({
    List<Map<String, dynamic>>? members,
    Map<String, dynamic>? settings,
    bool? isLoading,
    String? error,
  }) {
    return ConversationMembersState(
      members: members ?? this.members,
      settings: settings ?? this.settings,
      isLoading: isLoading ?? this.isLoading,
      error: error,
    );
  }
}

/// 会话成员及设置的 Notifier（family by conversationId）
/// 提供乐观更新写操作，失败时自动回滚
class ConversationMembersNotifier
    extends StateNotifier<ConversationMembersState> {
  ConversationMembersNotifier(
    this._repo,
    this._conversationId,
    this._currentUserId,
  ) : super(const ConversationMembersState(isLoading: true)) {
    load();
  }

  final ChatRepository _repo;
  final String _conversationId;
  final String _currentUserId;

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
      final members = (results[0] as List<Map<String, dynamic>>)
          .map((member) {
            final next = Map<String, dynamic>.from(member);
            final userId = (next['userId'] ?? next['profileSubjectId'] ?? '')
                .toString();
            next['isCurrentUser'] = userId == _currentUserId;
            return next;
          })
          .toList(growable: false);
      state = state.copyWith(
        members: members,
        settings: results[1] as Map<String, dynamic>,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: e.toString());
    }
  }

  /// 乐观更新管理员列表；失败时回滚
  Future<void> updateGroupAdmins(List<String> adminIds) async {
    final previous = state;
    state = state.copyWith(members: _applyAdminChange(state.members, adminIds));
    try {
      await _repo.updateGroupAdmins(_conversationId, adminIds);
    } catch (e) {
      state = previous;
      rethrow;
    }
  }

  /// 乐观更新群主转让；失败时回滚
  Future<void> transferOwnership(String newOwnerId) async {
    final previous = state;
    state = state.copyWith(
      members: _applyOwnerTransfer(state.members, newOwnerId),
    );
    try {
      await _repo.transferOwnership(_conversationId, newOwnerId);
    } catch (e) {
      state = previous;
      rethrow;
    }
  }

  /// 乐观更新群组设置；失败时回滚
  Future<void> updateSettings(Map<String, dynamic> settings) async {
    final previous = state;
    state = state.copyWith(settings: {...state.settings, ...settings});
    try {
      await _repo.updateGroupSettings(_conversationId, settings);
    } catch (e) {
      state = previous;
      rethrow;
    }
  }

  static List<Map<String, dynamic>> _applyAdminChange(
    List<Map<String, dynamic>> members,
    List<String> adminIds,
  ) {
    return members.map((m) {
      if (m['role'] == 'owner') return Map<String, dynamic>.from(m);
      final updated = Map<String, dynamic>.from(m);
      updated['role'] = adminIds.contains(m['userId']) ? 'admin' : 'member';
      return updated;
    }).toList();
  }

  static List<Map<String, dynamic>> _applyOwnerTransfer(
    List<Map<String, dynamic>> members,
    String newOwnerId,
  ) {
    return members.map((m) {
      final updated = Map<String, dynamic>.from(m);
      if (m['isCurrentUser'] == true) updated['role'] = 'member';
      if (m['userId'] == newOwnerId) updated['role'] = 'owner';
      return updated;
    }).toList();
  }
}

/// 会话成员与设置的全局共享 Provider（family by conversationId）
final conversationMembersProvider =
    StateNotifierProvider.family<
      ConversationMembersNotifier,
      ConversationMembersState,
      String
    >(
      (ref, conversationId) => ConversationMembersNotifier(
        ref.watch(chatRepositoryProvider),
        conversationId,
        ref.watch(currentUserIdProvider),
      ),
    );
