import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_access.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle_group_membership/application/public/circle_group_membership_flow.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 默认公共群成员关系：真实查询当前 Persona，并提供显式申请加入/退出动作。
class CircleGroupMembershipPanel extends StatefulWidget {
  const CircleGroupMembershipPanel({
    super.key,
    required this.circleId,
    required this.group,
    required this.access,
    required this.isDark,
  });

  final String circleId;
  final CircleGroupSlice group;
  final CircleGroupMembershipAccess access;
  final bool isDark;

  @override
  State<CircleGroupMembershipPanel> createState() =>
      _CircleGroupMembershipPanelState();
}

class _CircleGroupMembershipPanelState
    extends State<CircleGroupMembershipPanel> {
  late CircleGroupMembershipFlow _flow;
  CircleGroupMembershipViewState _state =
      const CircleGroupMembershipViewState.initial();

  @override
  void initState() {
    super.initState();
    _bindFlow();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_flow.load());
    });
  }

  @override
  void didUpdateWidget(covariant CircleGroupMembershipPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.circleId == widget.circleId &&
        oldWidget.group.groupId == widget.group.groupId &&
        identical(oldWidget.access, widget.access)) {
      return;
    }
    _flow.dispose();
    _state = const CircleGroupMembershipViewState.initial();
    _bindFlow();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) unawaited(_flow.load());
    });
  }

  @override
  void dispose() {
    _flow.dispose();
    super.dispose();
  }

  void _bindFlow() {
    _flow = CircleGroupMembershipFlow(
      circleId: widget.circleId,
      groupId: widget.group.groupId,
      access: widget.access,
      onStateChanged: (state) {
        if (mounted) setState(() => _state = state);
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_state.status == CircleGroupMembershipViewStatus.initial ||
        _state.status == CircleGroupMembershipViewStatus.loading) {
      return AppRequestFeedback.section(
        key: const ValueKey<String>('circle-group-membership-loading'),
      );
    }
    if (_state.status == CircleGroupMembershipViewStatus.failed) {
      return _errorCard();
    }

    final foreground = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final border = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );
    final action = _actionForState();
    return Semantics(
      container: true,
      label: CommunityText.circleGroupMembershipTitle,
      child: Container(
        key: const ValueKey<String>('circle-group-membership-panel'),
        margin: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
        padding: EdgeInsets.all(AppSpacing.containerMd),
        decoration: BoxDecoration(
          color: AppColors.iosProfileSurface(context),
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          border: Border.all(
            color: border.withValues(alpha: widget.isDark ? 0.24 : 0.12),
            width: AppSpacing.hairline,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              CommunityText.circleGroupMembershipTitle,
              style: TextStyle(
                color: foreground,
                fontSize: AppTypography.base,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.xs),
            Text(
              widget.group.name,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(color: secondary, fontSize: AppTypography.sm),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              _statusText(),
              key: const ValueKey<String>('circle-group-membership-status'),
              style: TextStyle(
                color: secondary,
                fontSize: AppTypography.sm,
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
            if (_state.error != null) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              _errorCard(),
            ],
            if (action != null) ...<Widget>[
              SizedBox(height: AppSpacing.containerSm),
              SizedBox(
                width: double.infinity,
                child: CupertinoButton.filled(
                  key: ValueKey<String>(action.key),
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerMd,
                    vertical: AppSpacing.containerSm,
                  ),
                  onPressed: _state.isMutating ? null : action.onPressed,
                  child: _state.isMutating
                      ? AppRequestFeedback.inline(
                          indicatorColor: CupertinoColors.white,
                        )
                      : Text(action.label),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _errorCard() {
    final error = _state.error;
    if (error == null) return const SizedBox.shrink();
    return AppSectionErrorCard(
      semantic: ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: error,
          category: _state.status == CircleGroupMembershipViewStatus.failed
              ? UiErrorCategory.sectionLoad
              : UiErrorCategory.backgroundAction,
          scope: UiErrorScope.section,
        ),
      ),
      margin: EdgeInsets.zero,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _flow.retry();
        }
      },
    );
  }

  String _statusText() => switch (_state.status) {
    CircleGroupMembershipViewStatus.notJoined =>
      widget.group.joinPolicy == CircleGroupJoinPolicy.inviteOnly
          ? CommunityText.circleGroupMembershipInviteOnly
          : CommunityText.circleGroupMembershipNotJoined,
    CircleGroupMembershipViewStatus.pending =>
      CommunityText.circleGroupMembershipPending,
    CircleGroupMembershipViewStatus.active =>
      _state.role == CircleGroupMembershipRole.owner
          ? CommunityText.circleGroupMembershipOwner
          : CommunityText.circleGroupMembershipActive,
    CircleGroupMembershipViewStatus.rejected =>
      CommunityText.circleGroupMembershipRejected,
    CircleGroupMembershipViewStatus.left =>
      CommunityText.circleGroupMembershipLeft,
    CircleGroupMembershipViewStatus.removed =>
      CommunityText.circleGroupMembershipRemoved,
    CircleGroupMembershipViewStatus.initial ||
    CircleGroupMembershipViewStatus.loading ||
    CircleGroupMembershipViewStatus.failed => CommunityText.noData,
  };

  _MembershipAction? _actionForState() {
    if (_state.canApply &&
        widget.group.joinPolicy != CircleGroupJoinPolicy.inviteOnly) {
      return _MembershipAction(
        key: 'circle-group-membership-apply',
        label: CommunityText.circleGroupMembershipApply,
        onPressed: () => unawaited(_flow.apply()),
      );
    }
    if (_state.canLeave) {
      return _MembershipAction(
        key: 'circle-group-membership-leave',
        label: CommunityText.circleGroupMembershipLeave,
        onPressed: () => unawaited(_flow.leave()),
      );
    }
    return null;
  }
}

final class _MembershipAction {
  const _MembershipAction({
    required this.key,
    required this.label,
    required this.onPressed,
  });

  final String key;
  final String label;
  final VoidCallback onPressed;
}
