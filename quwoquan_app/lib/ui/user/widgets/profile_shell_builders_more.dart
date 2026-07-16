part of 'profile_shell.dart';

extension _ProfileShellBuildersMore on _ProfileShellState {
  /// 举报用户：登录门保障 + 原因选择，经类型化 command capability 走 Remote。
  void _gatedReportUser(BuildContext context) {
    runWhenLoggedIn(ref, context, AuthGateReason.report, () async {
      final reason = await showAppActionSheet<_ProfileReportReason>(
        context,
        title: UITextConstants.profileReportReasonTitle,
        sections: [
          AppActionSheetSection<_ProfileReportReason>(
            items: _ProfileReportReason.values
                .map(
                  (r) => AppActionSheetItem<_ProfileReportReason>(
                    value: r,
                    label: r.label,
                  ),
                )
                .toList(growable: false),
          ),
        ],
      );
      if (reason == null || !context.mounted) return;
      try {
        await ref
            .read(userProfileContentReportCommandWriterProvider)
            .createReport(
              CreateContentReportCommand(
                targetId: widget.userId,
                targetType: ContentReportTargetType.user,
                reason: reason.reason,
              ),
            );
        if (context.mounted) {
          AppToast.show(context, UITextConstants.commentReportSubmitted);
        }
      } catch (error) {
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
}
