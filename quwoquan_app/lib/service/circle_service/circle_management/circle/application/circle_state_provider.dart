import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/errors/generated/circle/circle_membership_errors.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/domain/circle_stats_view_data.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/domain/circle_tab.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 圈子内用户角色
enum CircleRole { owner, admin, member, visitor }

CircleRole _circleRoleFromRaw(dynamic value) {
  return switch ((value ?? '').toString().trim().toLowerCase()) {
    'owner' => CircleRole.owner,
    'admin' => CircleRole.admin,
    'member' => CircleRole.member,
    _ => CircleRole.visitor,
  };
}

class CircleState {
  const CircleState({
    required this.circleId,
    this.circleData,
    this.defaultPublicGroup,
    this.role = CircleRole.visitor,
    this.joinStatus = 'none',
    this.membershipVersion,
    this.activeTabType = 'works',
    this.activeSubTab = CircleCreationSubTab.all,
    this.activeWorkFormat = CircleCreationWorkFormat.all,
    this.sortMode = CreationSortMode.latest,
    this.viewMode = CreationViewMode.grid,
    this.isLoading = false,
    this.loadError,
    this.circleStats = CircleStatsViewData.empty,
  });

  final String circleId;
  final Circle? circleData;
  final CircleGroupSlice? defaultPublicGroup;
  final CircleRole role;
  final String joinStatus;
  final int? membershipVersion;
  final String activeTabType;
  final CircleCreationSubTab activeSubTab;
  final CircleCreationWorkFormat activeWorkFormat;
  final CreationSortMode sortMode;
  final CreationViewMode viewMode;
  final bool isLoading;
  final Object? loadError;
  final CircleStatsViewData circleStats;

  CircleState copyWith({
    Circle? circleData,
    CircleGroupSlice? defaultPublicGroup,
    CircleRole? role,
    String? joinStatus,
    int? membershipVersion,
    bool clearMembershipVersion = false,
    String? activeTabType,
    CircleCreationSubTab? activeSubTab,
    CircleCreationWorkFormat? activeWorkFormat,
    CreationSortMode? sortMode,
    CreationViewMode? viewMode,
    bool? isLoading,
    Object? loadError,
    bool clearLoadError = false,
    CircleStatsViewData? circleStats,
  }) {
    return CircleState(
      circleId: circleId,
      circleData: circleData ?? this.circleData,
      defaultPublicGroup: defaultPublicGroup ?? this.defaultPublicGroup,
      role: role ?? this.role,
      joinStatus: joinStatus ?? this.joinStatus,
      membershipVersion: clearMembershipVersion
          ? null
          : (membershipVersion ?? this.membershipVersion),
      activeTabType: activeTabType ?? this.activeTabType,
      activeSubTab: activeSubTab ?? this.activeSubTab,
      activeWorkFormat: activeWorkFormat ?? this.activeWorkFormat,
      sortMode: sortMode ?? this.sortMode,
      viewMode: viewMode ?? this.viewMode,
      isLoading: isLoading ?? this.isLoading,
      loadError: clearLoadError ? null : (loadError ?? this.loadError),
      circleStats: circleStats ?? this.circleStats,
    );
  }
}

class CircleStateNotifier extends Notifier<CircleState> {
  CircleStateNotifier(this._circleId);

  final String _circleId;

  @override
  CircleState build() {
    Future.microtask(loadCircle);
    return CircleState(circleId: _circleId).copyWith(isLoading: true);
  }

  Future<void> loadCircle() async {
    if (!ref.mounted) return;
    if (state.circleData == null) {
      state = CircleState(circleId: _circleId).copyWith(isLoading: true);
    } else {
      state = state.copyWith(isLoading: true, clearLoadError: true);
    }
    try {
      final circleQuery = ref.read(circleDetailQueryProvider);
      final detail = await circleQuery.get(
        CircleDetailQuery(circleId: _circleId),
      );
      if (!ref.mounted) return;
      state = state.copyWith(circleData: detail);
      final stats = await circleQuery.stats(
        CircleStatsQuery(circleId: _circleId),
      );
      if (!ref.mounted) return;
      CircleMembershipSlice? membership;
      if (ref.read(resolvedOwnerUserIdProvider).trim().isNotEmpty) {
        await ref.read(activePersonaContextProvider.future);
        if (!ref.mounted) return;
        try {
          membership = await ref
              .read(circleDetailMembershipQueryProvider)
              .getMyMembership(MyCircleMembershipQuery(circleId: _circleId));
          if (!ref.mounted) return;
        } on CloudException catch (error) {
          if (error.domainErrorCode?.value !=
              CircleMembershipErrorCode.membershipNotFound) {
            rethrow;
          }
        }
      }
      if (!ref.mounted) return;
      CircleGroupSlice? defaultGroup;
      final defaultGroupId = detail.defaultPublicGroupId?.trim() ?? '';
      if (defaultGroupId.isNotEmpty && membership != null) {
        defaultGroup = await ref
            .read(circleDetailGroupQueryProvider)
            .get(
              CircleGroupQuery(circleId: _circleId, groupId: defaultGroupId),
            );
        if (!ref.mounted) return;
      }
      state = state.copyWith(
        circleData: detail,
        defaultPublicGroup: defaultGroup,
        role: _circleRoleFromRaw(membership?.role.name),
        joinStatus: membership == null
            ? 'none'
            : membership.state == CircleMembershipState.active
            ? 'joined'
            : membership.state.name,
        membershipVersion: membership?.version,
        clearMembershipVersion: membership == null,
        circleStats: CircleStatsViewData.fromWire(stats),
        isLoading: false,
        clearLoadError: true,
      );
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, loadError: e);
    }
  }

  void setActiveTab(String type) {
    state = state.copyWith(activeTabType: type);
  }

  void setSubTab(CircleCreationSubTab tab) {
    state = state.copyWith(
      activeSubTab: tab,
      activeWorkFormat: CircleCreationWorkFormat.all,
    );
  }

  void setWorkFormat(CircleCreationWorkFormat format) {
    state = state.copyWith(activeWorkFormat: format);
  }

  void setSortMode(CreationSortMode mode) {
    state = state.copyWith(sortMode: mode);
  }

  void setViewMode(CreationViewMode mode) {
    state = state.copyWith(viewMode: mode);
  }

  Future<void> joinCircle() async {
    final previousStatus = state.joinStatus;
    final previousVersion = state.membershipVersion;
    final joinPolicy = state.circleData?.joinPolicy ?? CircleJoinPolicy.open;
    if (joinPolicy == CircleJoinPolicy.inviteOnly) {
      return;
    }
    final nextJoinStatus = switch (joinPolicy) {
      CircleJoinPolicy.open => 'joined',
      CircleJoinPolicy.approval => 'pending',
      CircleJoinPolicy.inviteOnly => previousStatus,
    };
    state = state.copyWith(joinStatus: nextJoinStatus, clearLoadError: true);
    try {
      await ref.read(activePersonaContextProvider.future);
      final result = await ref
          .read(circleDetailMembershipCommandWriterProvider)
          .join(JoinCircleMembershipCommand(circleId: _circleId));
      state = state.copyWith(
        role: _circleRoleFromRaw(result.role.name),
        joinStatus: result.state == CircleMembershipState.active
            ? 'joined'
            : result.state.name,
        membershipVersion: result.version,
        clearLoadError: true,
      );
      if (result.state == CircleMembershipState.active &&
          !result.idempotentReplay) {
        _appendBehaviorFact(BehaviorEventType.joinCircle);
      }
      if (result.state == CircleMembershipState.active) {
        await _autoJoinDefaultPublicGroup();
      }
    } catch (error) {
      state = state.copyWith(
        joinStatus: previousStatus,
        membershipVersion: previousVersion,
        clearMembershipVersion: previousVersion == null,
        loadError: error,
      );
    }
  }

  /// 入圈即入群：加入成功后自动申请默认公共群（open 群即时 active，
  /// approval 群进入待审，inviteOnly 不申请）。群侧失败不回滚圈子加入——
  /// 加入事实已成立，讨论区成员面板仍保留手动申请入口，失败进全局异常遥测。
  Future<void> _autoJoinDefaultPublicGroup() async {
    final defaultGroupId = state.circleData?.defaultPublicGroupId?.trim() ?? '';
    if (defaultGroupId.isEmpty) {
      return;
    }
    try {
      final group = await ref
          .read(circleDetailGroupQueryProvider)
          .get(CircleGroupQuery(circleId: _circleId, groupId: defaultGroupId));
      if (!ref.mounted) return;
      state = state.copyWith(defaultPublicGroup: group);
      if (group.joinPolicy == CircleGroupJoinPolicy.inviteOnly) {
        return;
      }
      final access = ref.read(circleDetailGroupMembershipAccessProvider);
      final mine = await access.findMy(
        MyCircleGroupMembershipQuery(
          circleId: _circleId,
          groupId: defaultGroupId,
        ),
      );
      if (!ref.mounted) return;
      final canApply =
          mine == null ||
          mine.state == CircleGroupMembershipState.left ||
          mine.state == CircleGroupMembershipState.removed ||
          mine.state == CircleGroupMembershipState.rejected;
      if (!canApply) {
        return;
      }
      await access.apply(
        ApplyCircleGroupMembershipCommand(
          circleId: _circleId,
          groupId: defaultGroupId,
        ),
      );
    } catch (error, stackTrace) {
      unawaited(
        ref
            .read(exceptionTelemetryPortProvider)
            .recordGlobalException(
              source: 'circle.membership.auto_join_default_group',
              exceptionText: error.toString(),
              stackText: stackTrace.toString(),
            ),
      );
    }
  }

  /// 退出圈子（App 侧编排，成功返回 true）：先退默认公共群（active 且非群主），
  /// 再退圈。群退出失败整体中止并回滚——否则退圈后讨论区按成员资格封禁，
  /// 用户将永久失去「退出群聊」入口（Chat 侧圈群治理只回跳圈子）。
  Future<bool> leaveCircle() async {
    final previousStatus = state.joinStatus;
    final previousRole = state.role;
    final previousVersion = state.membershipVersion;
    try {
      await _leaveDefaultPublicGroupFirst();
      state = state.copyWith(
        joinStatus: 'none',
        role: CircleRole.visitor,
        clearMembershipVersion: true,
        clearLoadError: true,
      );
      final result = await ref
          .read(circleDetailMembershipCommandWriterProvider)
          .leave(LeaveCircleMembershipCommand(circleId: _circleId));
      state = state.copyWith(
        joinStatus: result.state.name,
        role: CircleRole.visitor,
        membershipVersion: result.version,
        clearLoadError: true,
      );
      if (!result.idempotentReplay) {
        _appendBehaviorFact(BehaviorEventType.leaveCircle);
      }
      return true;
    } catch (error) {
      state = state.copyWith(
        joinStatus: previousStatus,
        role: previousRole,
        membershipVersion: previousVersion,
        clearMembershipVersion: previousVersion == null,
        loadError: error,
      );
      return false;
    }
  }

  Future<void> _leaveDefaultPublicGroupFirst() async {
    final groupId =
        state.defaultPublicGroup?.groupId.trim() ??
        state.circleData?.defaultPublicGroupId?.trim() ??
        '';
    if (groupId.isEmpty) {
      return;
    }
    final access = ref.read(circleDetailGroupMembershipAccessProvider);
    final mine = await access.findMy(
      MyCircleGroupMembershipQuery(circleId: _circleId, groupId: groupId),
    );
    if (mine == null || mine.state != CircleGroupMembershipState.active) {
      return;
    }
    // 群主不可退群（owner 保护由群治理拥有）；此处不阻断退圈。
    if (mine.role == CircleGroupMembershipRole.owner) {
      return;
    }
    await access.leave(
      LeaveCircleGroupMembershipCommand(circleId: _circleId, groupId: groupId),
    );
  }

  /// 行为事实是推荐 HotPath 的 fire-and-forget 信号：
  /// 失败不回滚交互，经全局异常遥测观测通道兜底。
  void _appendBehaviorFact(BehaviorEventType eventType) {
    if (ref.read(resolvedOwnerUserIdProvider).trim().isEmpty) {
      return;
    }
    unawaited(
      ref
          .read(circleDetailBehaviorFactWriterProvider)
          .append(
            AppendCircleBehaviorFactCommand(
              circleId: _circleId,
              eventType: eventType,
            ),
          )
          .catchError((Object error, StackTrace stackTrace) {
            unawaited(
              ref
                  .read(exceptionTelemetryPortProvider)
                  .recordGlobalException(
                    source: 'circle.behavior.${eventType.wireName}',
                    exceptionText: error.toString(),
                    stackText: stackTrace.toString(),
                  ),
            );
          }),
    );
  }

  /// 更新走命名迁移命令；回执只含 circleId/version/status，
  /// 展示态经 loadCircle 从服务端详情读回（单一真相源，不做本地 map 合并）。
  Future<bool> updateCircleDetails(
    UpdateCircleCommand command,
    UpdateCircleSectionsCommand sectionsCommand,
  ) async {
    try {
      await ref.read(activePersonaContextProvider.future);
      await ref
          .read(circleDetailCircleLifecycleCommandWriterProvider)
          .updateCircle(command);
      await ref
          .read(circleDetailCircleConfigurationCommandWriterProvider)
          .updateCircleSections(sectionsCommand);
      await loadCircle();
      return state.loadError == null;
    } catch (e) {
      state = state.copyWith(loadError: e);
      return false;
    }
  }
}

final circleStateProvider =
    NotifierProvider.family<CircleStateNotifier, CircleState, String>(
      CircleStateNotifier.new,
    );

class CircleDirectoryRefreshNotifier extends Notifier<int> {
  @override
  int build() => 0;

  void bump() => state++;
}

final circleDirectoryRefreshProvider =
    NotifierProvider<CircleDirectoryRefreshNotifier, int>(
      CircleDirectoryRefreshNotifier.new,
    );
