part of 'home_multi_form_feed.dart';

extension _HomeMultiFormFeedReportActions on HomeMultiFormFeed {
  Future<void> _requestHomePostReport(
    BuildContext context,
    WidgetRef ref,
    ContentPostViewData post,
  ) async {
    final reason = await showContentReportReasonSheet(context);
    if (reason == null || !context.mounted) {
      return;
    }
    if (ref.read(authSessionControllerProvider).isAuthenticated) {
      await _submitHomePostReport(context, ref, post, reason);
      return;
    }
    final accepted = ref
        .read(authContinuationProvider.notifier)
        .set(
          SubmitContentReportContinuation(
            postId: post.id,
            surface: ContentReportContinuationSurface.homeFeed,
            reason: reason,
          ),
          ownerToken: 'home-feed-report:${post.id}',
        );
    if (!accepted) {
      return;
    }
    unawaited(
      requireLogin(
        ref,
        context,
        AuthGateReason.report,
        dismissFallback: AppRoutePaths.home,
        dismissPolicy: LoginDismissPolicy.safeFallback,
      ),
    );
  }

  void _scheduleHomeReportContinuationResume(
    BuildContext context,
    WidgetRef ref,
    List<ContentPostViewData> posts, {
    int remainingFrames = 30,
  }) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!context.mounted ||
          !ref.read(authSessionControllerProvider).isAuthenticated) {
        return;
      }
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) {
        if (remainingFrames > 0) {
          _scheduleHomeReportContinuationResume(
            context,
            ref,
            posts,
            remainingFrames: remainingFrames - 1,
          );
        }
        return;
      }
      final controller = ref.read(authContinuationProvider.notifier);
      final pending = controller.take<SubmitContentReportContinuation>();
      if (pending != null) {
        if (pending.surface != ContentReportContinuationSurface.homeFeed) {
          controller.set(pending);
          return;
        }
        ContentPostViewData? matched;
        for (final post in posts) {
          if (post.id == pending.postId) {
            matched = post;
            break;
          }
        }
        if (matched != null) {
          unawaited(
            _submitHomePostReport(context, ref, matched, pending.reason),
          );
        } else {
          controller.set(pending);
        }
        return;
      }
      final moderation = controller.take<ContentModerationContinuation>();
      if (moderation == null) return;
      if (moderation.surface != ContentModerationContinuationSurface.homeFeed) {
        controller.set(moderation);
        return;
      }
      ContentPostViewData? matched;
      for (final post in posts) {
        if (post.id == moderation.postId) {
          matched = post;
          break;
        }
      }
      if (matched == null) {
        controller.set(moderation);
        return;
      }
      switch (moderation.action) {
        case ContentModerationContinuationAction.blockAuthor:
          unawaited(_applyHomeBlockAuthor(context, ref, matched));
        case ContentModerationContinuationAction.blockKeyword:
          final keyword = moderation.keyword?.trim() ?? '';
          if (keyword.isNotEmpty) {
            unawaited(_applyHomeBlockKeyword(context, ref, matched, keyword));
          }
      }
    });
  }

  Future<void> _submitHomePostReport(
    BuildContext context,
    WidgetRef ref,
    ContentPostViewData post,
    ReportReason reason,
  ) async {
    final journeyTracker = ref.read(journeyEventTrackerProvider);
    final startedAt = DateTime.now();
    try {
      await ref
          .read(homeFeedContentReportCommandWriterProvider)
          .createReport(
            CreateContentReportCommand(
              targetId: post.id,
              targetType: ReportTargetType.post,
              reason: reason,
            ),
          );
      await journeyTracker.trackAction(
        journey: 'content_report',
        action: 'submit_report',
        pageName: 'home_multi_form_feed',
        payload: <String, Object?>{
          'result': 'success',
          'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
        },
      );
      if (!context.mounted) return;
      _dismissFeedPost(
        context,
        ref,
        post.id,
        toast: ContentText.reportSubmittedViewProgress,
      );
    } catch (error) {
      await journeyTracker.trackAction(
        journey: 'content_report',
        action: 'submit_report',
        pageName: 'home_multi_form_feed',
        error: error,
        payload: <String, Object?>{
          'result': 'failure',
          'failReasonCode': error is CloudException
              ? (error.code ?? error.type.name)
              : error.runtimeType.toString(),
          'durationMs': DateTime.now().difference(startedAt).inMilliseconds,
        },
      );
      if (!context.mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.global,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry ||
              action.type == UiErrorActionType.resubmit) {
            await _submitHomePostReport(context, ref, post, reason);
          }
        },
      );
    }
  }
}
