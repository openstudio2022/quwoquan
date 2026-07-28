import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CircleMembershipSlice,
        DecideCircleMembershipCommand,
        PendingCircleMembershipListQuery;

/// 圈子加入审批队列（owner/admin）：消费 ListPendingCircleMemberships，
/// Approve/Reject 走圈子级审批命令（metadata `circle.circle_membership.*`）。
///
/// 入口：圈子主页更多菜单「加入审批」（仅 owner/admin 可见）。
class CircleMembershipApprovalPage extends ConsumerStatefulWidget {
  const CircleMembershipApprovalPage({super.key, required this.circleId});

  final String circleId;

  @override
  ConsumerState<CircleMembershipApprovalPage> createState() =>
      _CircleMembershipApprovalPageState();
}

class _CircleMembershipApprovalPageState
    extends ConsumerState<CircleMembershipApprovalPage> {
  static const int _pageLimit = 50;

  final List<CircleMembershipSlice> _pendingItems = <CircleMembershipSlice>[];
  final Set<String> _decidingPersonaIds = <String>{};
  String? _nextCursor;
  bool _isLoading = true;
  bool _isLoadingMore = false;
  UiErrorSemantic? _pageErrorSemantic;

  // R20：管理工具页曝光/停留走 product_action journey 通道；
  // dispose 阶段禁止再解析 ref，进入时缓存 tracker。
  late final DateTime _pageEnteredAt;
  JourneyEventTracker? _journeyTracker;

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    unawaited(_loadPending(reset: true));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _journeyTracker = ref.read(journeyEventTrackerProvider);
      unawaited(
        _journeyTracker!.trackAction(
          journey: 'circle_manage',
          action: 'approval_page_enter',
          pageName: 'circle_membership_approval',
          targetType: 'circle',
          targetKey: widget.circleId,
        ),
      );
    });
  }

  @override
  void dispose() {
    final tracker = _journeyTracker;
    if (tracker != null) {
      unawaited(
        tracker.trackAction(
          journey: 'circle_manage',
          action: 'approval_page_exit',
          pageName: 'circle_membership_approval',
          targetType: 'circle',
          targetKey: widget.circleId,
          payload: {
            'durationMs': DateTime.now()
                .difference(_pageEnteredAt)
                .inMilliseconds,
          },
        ),
      );
    }
    super.dispose();
  }

  Future<void> _loadPending({required bool reset}) async {
    if (reset) {
      setState(() {
        _isLoading = true;
        _pageErrorSemantic = null;
      });
    } else {
      if (_isLoadingMore || _nextCursor == null) {
        return;
      }
      setState(() => _isLoadingMore = true);
    }
    try {
      final page = await ref
          .read(circleDetailPendingMembershipQueryProvider)
          .listPendingMemberships(
            PendingCircleMembershipListQuery(
              circleId: widget.circleId,
              cursor: reset ? null : _nextCursor,
              limit: _pageLimit,
            ),
          );
      if (!mounted) {
        return;
      }
      setState(() {
        if (reset) {
          _pendingItems
            ..clear()
            ..addAll(page.items);
        } else {
          _pendingItems.addAll(page.items);
        }
        _nextCursor = page.nextCursor;
        _isLoading = false;
        _isLoadingMore = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isLoading = false;
        _isLoadingMore = false;
        _pageErrorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    }
  }

  Future<void> _decide(
    CircleMembershipSlice item, {
    required bool approved,
  }) async {
    if (_decidingPersonaIds.contains(item.personaId)) {
      return;
    }
    setState(() => _decidingPersonaIds.add(item.personaId));
    final command = DecideCircleMembershipCommand(
      circleId: widget.circleId,
      personaId: item.personaId,
    );
    try {
      final writer = ref.read(circleDetailMembershipModerationWriterProvider);
      final result = approved
          ? await writer.approve(command)
          : await writer.reject(command);
      if (!mounted) {
        return;
      }
      setState(() {
        _pendingItems.removeWhere(
          (pending) => pending.personaId == item.personaId,
        );
        _decidingPersonaIds.remove(item.personaId);
      });
      AppToast.show(
        context,
        approved
            ? CommunityText.circleApprovalApproved
            : CommunityText.circleApprovalRejected,
      );
      unawaited(
        _journeyTracker?.trackAction(
              journey: 'circle_manage',
              action: approved ? 'approve_member' : 'reject_member',
              pageName: 'circle_membership_approval',
              targetType: 'circle',
              targetKey: widget.circleId,
              payload: {
                'result': 'success',
                'idempotentReplay': result.idempotentReplay,
              },
            ) ??
            Future<void>.value(),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => _decidingPersonaIds.remove(item.personaId));
      // 状态冲突（已被其他管理员处理）时刷新队列，保持与云侧一致。
      if (error is CloudException) {
        unawaited(_loadPending(reset: true));
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: resolved);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bg = AppColors.iosPageBackground(context);
    return AppScaffold(
      backgroundColor: bg,
      navigationBar: AppNavigationBar(
        automaticallyImplyLeading: false,
        backgroundColor: bg,
        middle: Text(CommunityText.circleApprovalTitle),
        leading: AppNavigationBarIconButton(
          key: const ValueKey<String>('circle-approval-back'),
          icon: CupertinoIcons.back,
          onPressed: () => Navigator.of(context).maybePop(),
        ),
      ),
      body: _buildBody(context),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_isLoading) {
      return AppRequestFeedback.section();
    }
    final semantic = _pageErrorSemantic;
    if (semantic != null) {
      return AppPageErrorState(
        semantic: ensureRetryUiErrorSemantic(semantic),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadPending(reset: true);
          }
        },
      );
    }
    if (_pendingItems.isEmpty) {
      return _buildEmpty(context);
    }
    return CustomScrollView(
      slivers: [
        CupertinoSliverRefreshControl(
          onRefresh: () => _loadPending(reset: true),
        ),
        SliverPadding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerMd,
            vertical: AppSpacing.containerSm,
          ),
          sliver: SliverList.separated(
            itemCount: _pendingItems.length + (_nextCursor != null ? 1 : 0),
            separatorBuilder: (_, _) =>
                SizedBox(height: AppSpacing.intraGroupXs),
            itemBuilder: (context, index) {
              if (index >= _pendingItems.length) {
                unawaited(_loadPending(reset: false));
                return AppRequestFeedback.section();
              }
              return _buildPendingRow(context, _pendingItems[index]);
            },
          ),
        ),
      ],
    );
  }

  Widget _buildEmpty(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            CupertinoIcons.person_crop_circle_badge_checkmark,
            size: AppSpacing.iconLarge,
            color: AppColors.iosSecondaryLabel(context),
          ),
          SizedBox(height: AppSpacing.sm),
          Text(
            CommunityText.circleApprovalEmpty,
            key: const ValueKey<String>('circle-approval-empty'),
            style: TextStyle(
              fontSize: AppTypography.base,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPendingRow(BuildContext context, CircleMembershipSlice item) {
    final deciding = _decidingPersonaIds.contains(item.personaId);
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    return Container(
      key: ValueKey<String>('circle-approval-row-${item.personaId}'),
      padding: EdgeInsets.all(AppSpacing.containerSm),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  item.personaId,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    fontWeight: AppTypography.medium,
                    color: fg,
                  ),
                ),
                SizedBox(height: AppSpacing.xs),
                Text(
                  context.l10n.monthDayTemplate(
                    item.createdAt.month,
                    item.createdAt.day,
                  ),
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
          if (deciding)
            AppRequestFeedback.inline()
          else ...[
            CupertinoButton(
              key: ValueKey<String>('circle-approval-reject-${item.personaId}'),
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              onPressed: () => unawaited(_decide(item, approved: false)),
              child: Text(
                CommunityText.circleApprovalRejectAction,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColors.error,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.xs),
            CupertinoButton(
              key: ValueKey<String>(
                'circle-approval-approve-${item.personaId}',
              ),
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
              minimumSize: const Size(
                AppSpacing.minInteractiveSize,
                AppSpacing.minInteractiveSize,
              ),
              color: AppColors.primaryColor,
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              onPressed: () => unawaited(_decide(item, approved: true)),
              child: Text(
                CommunityText.circleApprovalApproveAction,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: AppColors.white,
                ),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
