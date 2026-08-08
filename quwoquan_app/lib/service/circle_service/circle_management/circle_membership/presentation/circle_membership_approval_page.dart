import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_membership/application/public/circle_membership_ports.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/observability/app_trace_context_store.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CircleMembershipCommandResult,
        CircleMembershipSlice,
        CircleMembershipState,
        DecideCircleMembershipCommand,
        PendingCircleMembershipListQuery;

/// 圈子加入审批队列（owner/admin）：消费 ListPendingCircleMemberships，
/// Approve/Reject 走圈子级审批命令（metadata `circle.circle_membership.*`）。
///
/// 入口：圈子主页更多菜单「加入审批」（仅 owner/admin 可见）。
class CircleMembershipApprovalPage extends StatefulWidget {
  const CircleMembershipApprovalPage({
    super.key,
    required this.circleId,
    required this.pendingMemberships,
    required this.moderationWriter,
    required this.journeyEventTracker,
  });

  final String circleId;
  final PendingCircleMemberships pendingMemberships;
  final CircleMembershipModeration moderationWriter;
  final JourneyEventTracker journeyEventTracker;

  @override
  State<CircleMembershipApprovalPage> createState() =>
      _CircleMembershipApprovalPageState();
}

class _CircleMembershipApprovalPageState
    extends State<CircleMembershipApprovalPage> {
  static const int _pageLimit = 50;

  final List<CircleMembershipSlice> _pendingItems = <CircleMembershipSlice>[];
  final Set<String> _decidingPersonaIds = <String>{};
  int _loadEpoch = 0;
  String? _nextCursor;
  bool _isLoading = true;
  bool _isLoadingMore = false;
  bool _hasConfirmedSnapshot = false;
  UiErrorSemantic? _pageErrorSemantic;
  UiErrorSemantic? _refreshErrorSemantic;
  UiErrorSemantic? _loadMoreErrorSemantic;

  // R20：管理工具页曝光/停留走 product_action journey 通道。
  late final DateTime _pageEnteredAt;

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    unawaited(_loadPending(reset: true));
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      unawaited(
        widget.journeyEventTracker.trackAction(
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
  void didUpdateWidget(covariant CircleMembershipApprovalPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.circleId == widget.circleId &&
        identical(oldWidget.pendingMemberships, widget.pendingMemberships)) {
      return;
    }
    _loadEpoch++;
    _pendingItems.clear();
    _decidingPersonaIds.clear();
    _nextCursor = null;
    _isLoading = true;
    _isLoadingMore = false;
    _hasConfirmedSnapshot = false;
    _pageErrorSemantic = null;
    _refreshErrorSemantic = null;
    _loadMoreErrorSemantic = null;
    unawaited(_loadPending(reset: true));
  }

  @override
  void dispose() {
    unawaited(
      widget.journeyEventTracker.trackAction(
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
    super.dispose();
  }

  Future<void> _loadPending({required bool reset}) async {
    late final int requestEpoch;
    late final String? requestCursor;
    if (reset) {
      requestEpoch = ++_loadEpoch;
      requestCursor = null;
      setState(() {
        _isLoading = !_hasConfirmedSnapshot;
        _isLoadingMore = false;
        _pageErrorSemantic = null;
        _refreshErrorSemantic = null;
        _loadMoreErrorSemantic = null;
      });
    } else {
      if (_isLoadingMore || _nextCursor == null) {
        return;
      }
      requestEpoch = _loadEpoch;
      requestCursor = _nextCursor;
      setState(() {
        _isLoadingMore = true;
        _loadMoreErrorSemantic = null;
      });
    }
    try {
      final page = await widget.pendingMemberships.listPendingMemberships(
        PendingCircleMembershipListQuery(
          circleId: widget.circleId,
          cursor: requestCursor,
          limit: _pageLimit,
        ),
      );
      if (!mounted || requestEpoch != _loadEpoch) {
        return;
      }
      final confirmedItems = reset
          ? _dedupePending(page.items)
          : _dedupePending(<CircleMembershipSlice>[
              ..._pendingItems,
              ...page.items,
            ]);
      setState(() {
        _pendingItems
          ..clear()
          ..addAll(confirmedItems);
        _nextCursor = _normalizedCursor(page.cursor);
        _isLoading = false;
        _isLoadingMore = false;
        _hasConfirmedSnapshot = true;
        _pageErrorSemantic = null;
        _refreshErrorSemantic = null;
        _loadMoreErrorSemantic = null;
      });
    } catch (error) {
      if (!mounted || requestEpoch != _loadEpoch) {
        return;
      }
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
      setState(() {
        _isLoading = false;
        _isLoadingMore = false;
        if (!reset) {
          _loadMoreErrorSemantic = semantic;
        } else if (_hasConfirmedSnapshot) {
          _refreshErrorSemantic = semantic;
        } else {
          _pageErrorSemantic = semantic;
        }
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
    final attempt = _CircleMembershipDecisionAttempt(
      circleId: widget.circleId,
      item: item,
      approved: approved,
      clientRequestId: AppTraceContextStore.instance.newRequestId(),
    );
    setState(() => _decidingPersonaIds.add(item.personaId));
    await _runDecisionAttempt(attempt);
  }

  Future<void> _runDecisionAttempt(
    _CircleMembershipDecisionAttempt attempt,
  ) async {
    final command = DecideCircleMembershipCommand(
      circleId: attempt.circleId,
      personaId: attempt.item.personaId,
    );
    try {
      final writer = widget.moderationWriter;
      if (writer is! ClientRequestBoundCircleMembershipModeration) {
        throw StateError(
          'Circle membership moderation writer does not accept clientRequestId',
        );
      }
      final result = attempt.approved
          ? await writer.approveWithClientRequestId(
              command,
              clientRequestId: attempt.clientRequestId,
            )
          : await writer.rejectWithClientRequestId(
              command,
              clientRequestId: attempt.clientRequestId,
            );
      if (!mounted || attempt.circleId != widget.circleId) {
        return;
      }
      _verifyDecisionAck(attempt, result);
      final snapshot = await _readBackPendingAfterDecision(attempt);
      if (!mounted || attempt.circleId != widget.circleId) {
        return;
      }
      setState(() {
        _pendingItems
          ..clear()
          ..addAll(snapshot);
        _nextCursor = null;
        _isLoading = false;
        _isLoadingMore = false;
        _hasConfirmedSnapshot = true;
        _pageErrorSemantic = null;
        _refreshErrorSemantic = null;
        _loadMoreErrorSemantic = null;
        _decidingPersonaIds.remove(attempt.item.personaId);
      });
      AppToast.show(
        context,
        attempt.approved
            ? CommunityText.circleApprovalApproved
            : CommunityText.circleApprovalRejected,
      );
      unawaited(
        widget.journeyEventTracker.trackAction(
          journey: 'circle_manage',
          action: attempt.approved ? 'approve_member' : 'reject_member',
          pageName: 'circle_membership_approval',
          targetType: 'circle',
          targetKey: widget.circleId,
          payload: {
            'result': 'success',
            'idempotentReplay': result.idempotentReplay,
          },
        ),
      );
    } catch (error) {
      if (!mounted || attempt.circleId != widget.circleId) {
        return;
      }
      await _showDecisionFailure(attempt, error);
    }
  }

  void _verifyDecisionAck(
    _CircleMembershipDecisionAttempt attempt,
    CircleMembershipCommandResult result,
  ) {
    final expectedState = attempt.approved
        ? CircleMembershipState.active
        : CircleMembershipState.rejected;
    if (result.membershipId != attempt.item.membershipId ||
        result.state != expectedState ||
        result.version <= attempt.item.version) {
      throw _CircleMembershipDecisionNotConverged(
        'typed ACK does not advance the target membership to the expected state',
      );
    }
  }

  Future<List<CircleMembershipSlice>> _readBackPendingAfterDecision(
    _CircleMembershipDecisionAttempt attempt,
  ) async {
    final readbackEpoch = ++_loadEpoch;
    if (mounted) {
      setState(() {
        _isLoadingMore = false;
        _loadMoreErrorSemantic = null;
      });
    }
    final collected = <CircleMembershipSlice>[];
    final seenCursors = <String>{};
    String? cursor;
    while (true) {
      final page = await widget.pendingMemberships.listPendingMemberships(
        PendingCircleMembershipListQuery(
          circleId: attempt.circleId,
          cursor: cursor,
          limit: _pageLimit,
        ),
      );
      if (!mounted ||
          attempt.circleId != widget.circleId ||
          readbackEpoch != _loadEpoch) {
        throw const _CircleMembershipDecisionNotConverged(
          'authoritative readback was superseded',
        );
      }
      collected.addAll(page.items);
      final nextCursor = _normalizedCursor(page.cursor);
      if (nextCursor == null) {
        break;
      }
      if (!seenCursors.add(nextCursor)) {
        throw const _CircleMembershipDecisionNotConverged(
          'authoritative readback returned a cursor loop',
        );
      }
      cursor = nextCursor;
    }
    final snapshot = _dedupePending(collected);
    final targetStillPending = snapshot.any(
      (pending) =>
          pending.membershipId == attempt.item.membershipId ||
          pending.personaId == attempt.item.personaId,
    );
    if (targetStillPending) {
      throw const _CircleMembershipDecisionNotConverged(
        'authoritative pending queue still contains the decision target',
      );
    }
    return snapshot;
  }

  Future<void> _showDecisionFailure(
    _CircleMembershipDecisionAttempt attempt,
    Object error,
  ) async {
    final resolved = ensureRetryUiErrorSemantic(
      runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      ),
    );
    var retryStarted = false;
    await AppActionErrorFeedback.show(
      context,
      semantic: resolved,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          retryStarted = true;
          await _runDecisionAttempt(attempt);
          return;
        }
        _finishDecisionAttempt(attempt);
      },
    );
    if (!retryStarted) {
      _finishDecisionAttempt(attempt);
    }
  }

  void _finishDecisionAttempt(_CircleMembershipDecisionAttempt attempt) {
    if (!mounted || attempt.circleId != widget.circleId) {
      return;
    }
    setState(() => _decidingPersonaIds.remove(attempt.item.personaId));
  }

  List<CircleMembershipSlice> _dedupePending(
    Iterable<CircleMembershipSlice> source,
  ) {
    final result = <CircleMembershipSlice>[];
    final indexByMembershipId = <String, int>{};
    final seenMembershipVersions = <String>{};
    for (final item in source) {
      final versionKey = '${item.membershipId}\u0000${item.version}';
      if (!seenMembershipVersions.add(versionKey)) {
        continue;
      }
      final existingIndex = indexByMembershipId[item.membershipId];
      if (existingIndex == null) {
        indexByMembershipId[item.membershipId] = result.length;
        result.add(item);
        continue;
      }
      if (item.version > result[existingIndex].version) {
        result[existingIndex] = item;
      }
    }
    return result;
  }

  String? _normalizedCursor(String? value) {
    final normalized = value?.trim();
    return normalized == null || normalized.isEmpty ? null : normalized;
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
    if (!_hasConfirmedSnapshot && semantic != null) {
      return AppPageErrorState(
        semantic: ensureRetryUiErrorSemantic(semantic),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _loadPending(reset: true);
            return _pageErrorSemantic == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    return CustomScrollView(
      slivers: [
        CupertinoSliverRefreshControl(
          onRefresh: () => _loadPending(reset: true),
        ),
        if (_refreshErrorSemantic case final refreshError?)
          SliverPadding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.containerSm,
              AppSpacing.containerMd,
              0,
            ),
            sliver: SliverToBoxAdapter(
              child: AppSectionErrorState(
                key: const ValueKey<String>('circle-approval-refresh-error'),
                semantic: ensureRetryUiErrorSemantic(refreshError),
                padding: EdgeInsets.all(AppSpacing.containerSm),
                onAction: (action) async {
                  if (_isRetryAction(action)) {
                    await _loadPending(reset: true);
                  }
                },
              ),
            ),
          ),
        if (_pendingItems.isEmpty)
          SliverFillRemaining(hasScrollBody: false, child: _buildEmpty(context))
        else
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
                  return _buildLoadMoreFooter();
                }
                return _buildPendingRow(context, _pendingItems[index]);
              },
            ),
          ),
      ],
    );
  }

  Widget _buildLoadMoreFooter() {
    final semantic = _loadMoreErrorSemantic;
    if (semantic != null) {
      return AppSectionErrorState(
        key: const ValueKey<String>('circle-approval-load-more-error'),
        semantic: ensureRetryUiErrorSemantic(semantic),
        padding: EdgeInsets.all(AppSpacing.containerSm),
        onAction: (action) async {
          if (_isRetryAction(action)) {
            await _loadPending(reset: false);
          }
        },
      );
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          _isLoadingMore ||
          _loadMoreErrorSemantic != null ||
          _nextCursor == null) {
        return;
      }
      unawaited(_loadPending(reset: false));
    });
    return AppRequestFeedback.section();
  }

  bool _isRetryAction(UiErrorAction action) =>
      action.type == UiErrorActionType.retry ||
      action.type == UiErrorActionType.resubmit;

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

final class _CircleMembershipDecisionAttempt {
  const _CircleMembershipDecisionAttempt({
    required this.circleId,
    required this.item,
    required this.approved,
    required this.clientRequestId,
  });

  final String circleId;
  final CircleMembershipSlice item;
  final bool approved;
  final String clientRequestId;
}

final class _CircleMembershipDecisionNotConverged implements Exception {
  const _CircleMembershipDecisionNotConverged(this.reason);

  final String reason;

  @override
  String toString() => 'CircleMembershipDecisionNotConverged: $reason';
}
