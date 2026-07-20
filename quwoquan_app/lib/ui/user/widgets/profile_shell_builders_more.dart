part of 'profile_shell.dart';

extension _ProfileShellBuildersMore on _ProfileShellState {
  /// 分享主页：昵称 + 简介 + 公网主页 HTTPS 链接经系统分享面板分发。
  /// 链接形态由 metadata link_templates codegen 提供，origin 来自运行时配置。
  Future<void> _shareProfile(BuildContext context) async {
    final state = ref.read(profileNotifierProvider(widget.userId));
    final profile = state.profile;
    final username = (profile?.username ?? '').trim().isNotEmpty
        ? profile!.username.trim()
        : widget.userId;
    final landingUrl = AppPublicContentLinks.publicWebUrlForPath(
      AppLinkTemplates.userWebPath(username),
    );
    final displayName = (profile?.displayName ?? '').trim();
    final bio = (profile?.bio ?? '').trim();
    final shareText = <String>[
      if (displayName.isNotEmpty) displayName,
      if (bio.isNotEmpty) bio,
      landingUrl,
    ].join('\n');
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    try {
      final result = await SharePlus.instance.share(
        ShareParams(
          title: UITextConstants.profileShareHomepage,
          subject: displayName.isNotEmpty
              ? displayName
              : UITextConstants.profileShareHomepage,
          text: shareText,
        ),
      );
      final shared = result.status == ShareResultStatus.success;
      await journeyTracker.trackAction(
        journey: 'profile_share',
        action: 'share_homepage',
        pageName: 'user_profile_shell',
        payload: {
          'result': shared ? 'success' : 'dismissed',
          'mode': widget.mode.name,
        },
      );
    } catch (error) {
      await journeyTracker.trackAction(
        journey: 'profile_share',
        action: 'share_homepage',
        pageName: 'user_profile_shell',
        payload: {
          'result': 'failure',
          'mode': widget.mode.name,
          'failReasonCode': error.runtimeType.toString(),
        },
      );
      if (context.mounted) {
        AppToast.show(context, ChatText.shareFailed);
      }
    }
  }

  /// 举报用户：登录门保障 + 原因选择，经类型化 command capability 走 Remote。
  void _gatedReportUser(BuildContext context) {
    runWhenLoggedIn(ref, context, AuthGateReason.report, () async {
      final reason = await showContentReportReasonSheet(context);
      if (reason == null || !context.mounted) return;
      final journeyTracker = ref.read(journeyEventTrackerProvider);
      final startedAt = DateTime.now();
      try {
        await ref
            .read(userProfileContentReportCommandWriterProvider)
            .createReport(
              CreateContentReportCommand(
                targetId: widget.userId,
                targetType: ContentReportTargetType.user,
                reason: reason,
              ),
            );
        await journeyTracker.trackAction(
          journey: 'content_report',
          action: 'submit_report',
          pageName: 'user_profile_shell',
          payload: {
            'result': 'success',
            'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
          },
        );
        if (context.mounted) {
          AppToast.show(context, UITextConstants.commentReportSubmitted);
        }
      } catch (error) {
        await journeyTracker.trackAction(
          journey: 'content_report',
          action: 'submit_report',
          pageName: 'user_profile_shell',
          payload: {
            'result': 'failure',
            'failReasonCode': error is CloudException
                ? (error.code ?? error.type.name)
                : error.runtimeType.toString(),
            'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
          },
        );
        if (!context.mounted) {
          return;
        }
        final resolved = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        );
        await AppActionErrorFeedback.show(context, semantic: resolved);
      }
    });
  }

  Future<void> _showMoreOptions(BuildContext context) async {
    final action = await showAppActionSheet<_ProfileMoreAction>(
      context,
      title: UITextConstants.profileMoreOptionsTitle,
      sections: const [
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.share,
              label: UITextConstants.share,
              icon: CupertinoIcons.arrowshape_turn_up_right,
            ),
          ],
        ),
        AppActionSheetSection<_ProfileMoreAction>(
          items: [
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.block,
              label: UITextConstants.profileBlockUser,
              icon: CupertinoIcons.person_crop_circle_badge_xmark,
            ),
            AppActionSheetItem<_ProfileMoreAction>(
              value: _ProfileMoreAction.report,
              label: UITextConstants.report,
              icon: CupertinoIcons.flag,
              isDestructive: true,
            ),
          ],
        ),
      ],
    );
    if (!context.mounted || action == null) {
      return;
    }
    switch (action) {
      case _ProfileMoreAction.share:
        unawaited(_shareProfile(context));
      case _ProfileMoreAction.block:
        _gatedBlockUser(context);
      case _ProfileMoreAction.report:
        _gatedReportUser(context);
    }
  }

  /// 拉黑用户：登录门保障 + 二次确认，经对象级 command writer 走 Remote。
  void _gatedBlockUser(BuildContext context) {
    runWhenLoggedIn(ref, context, AuthGateReason.blockUser, () async {
      final confirmed = await showAppActionSheet<bool>(
        context,
        title: UITextConstants.profileBlockConfirmTitle,
        message: UITextConstants.profileBlockConfirmMessage,
        sections: const [
          AppActionSheetSection<bool>(
            items: [
              AppActionSheetItem<bool>(
                value: true,
                label: UITextConstants.profileBlockUser,
                icon: CupertinoIcons.person_crop_circle_badge_xmark,
                isDestructive: true,
              ),
            ],
          ),
        ],
      );
      if (confirmed != true || !context.mounted) {
        return;
      }
      await _blockProfileUser(context);
    });
  }

  Future<void> _blockProfileUser(BuildContext context) async {
    final startedAt = DateTime.now();
    try {
      await ref
          .read(
            personaRelationshipBlockWriterProvider(AppUiSurfaces.profileHome),
          )
          .blockUser(BlockUserCommand(targetSubAccountId: widget.userId));
      ref.invalidate(profileNotifierProvider(widget.userId));
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'block_user',
              pageName: 'user_profile_shell',
              targetType: 'user',
              targetKey: widget.userId,
              payload: {
                'result': 'success',
                'durationMs': DateTime.now()
                    .difference(startedAt)
                    .inMilliseconds,
              },
            ),
      );
      if (!context.mounted) {
        return;
      }
      AppToast.show(context, UITextConstants.profileBlockSuccess);
      _leaveProfile(context);
    } catch (error) {
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'block_user',
              pageName: 'user_profile_shell',
              targetType: 'user',
              targetKey: widget.userId,
              payload: {
                'result': 'failure',
                'failReasonCode': error is CloudException
                    ? (error.code ?? error.type.name)
                    : error.runtimeType.toString(),
                'durationMs': DateTime.now()
                    .difference(startedAt)
                    .inMilliseconds,
              },
            ),
      );
      if (!context.mounted) {
        return;
      }
      final resolved = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(
        context,
        semantic: resolved,
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _blockProfileUser(context);
          }
        },
      );
    }
  }
}
