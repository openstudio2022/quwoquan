import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/design_system/media/media_aspect_ratio.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart'
    show AuthGateReason, LoginDismissPolicy, requireLogin, runWhenLoggedIn;
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show workBrowserContentReportCommandWriterProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CommentReactionType,
        CommentSort,
        CommentViewerRelation,
        CreateContentReportCommand,
        ReportReason,
        ReportTargetType;
import 'package:quwoquan_app/runtime/testing/test_keys.dart';
import 'package:quwoquan_app/runtime/observability/trackers/comment_observability.dart';
import 'package:quwoquan_app/design_system/formatters/compact_count_formatter.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/shell/actions/content_report_reason_sheet.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/service/content_service/content/comment/domain/comment_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/comment/application/comment_provider.dart';
import 'package:quwoquan_app/service/content_service/content/comment/presentation/comment_reaction_feedback.dart';

part 'comment_thread_rows.dart';
part 'comment_thread_atoms.dart';
part 'comment_item_actions.dart';

class CommentThreadView extends ConsumerStatefulWidget {
  const CommentThreadView({
    super.key,
    required this.postId,
    this.scrollController,
    this.onReplySelected,
    this.shrinkWrap = false,
    this.highlightCommentId,
    this.highlightReplyId,
  });

  final String postId;
  final ScrollController? scrollController;
  final ValueChanged<CommentViewData>? onReplySelected;

  /// 深链定位目标一级评论 id：列表加载后自动滚动到该评论并短暂高亮
  /// （我的-互动 / 通知中心点进评论使用）。
  final String? highlightCommentId;

  /// 深链定位目标二级回复 id。传入后会自动展开父评论的回复分页直到命中，
  /// 然后滚动到对应二级回复并短暂高亮。
  final String? highlightReplyId;

  /// 平铺模式：列表用 `shrinkWrap + NeverScrollable`，随父滚动流展开，
  /// 不再要求外部给定有界高度（文章内容平铺评论区使用）。
  final bool shrinkWrap;

  @override
  ConsumerState<CommentThreadView> createState() => _CommentThreadViewState();
}

class _CommentThreadViewState extends ConsumerState<CommentThreadView> {
  late final ScrollController _scrollController;
  bool _ownsController = false;
  bool _initialLoaded = false;

  final Map<String, GlobalKey> _commentItemKeys = <String, GlobalKey>{};
  final Map<String, GlobalKey> _replyItemKeys = <String, GlobalKey>{};
  String? _highlightedCommentId;
  String? _highlightedReplyId;

  /// 已完成解析（命中或翻尽未命中）的深链目标 key，避免重复触发。
  String? _resolvedHighlightKey;

  /// 深链解析（翻页 / 展开回复）是否进行中，避免并发重入。
  bool _highlightResolutionInFlight = false;

  /// 异常游标等极端情况下的翻页安全上限，杜绝死循环。
  static const int _maxDeepLinkPageScan = 200;
  Timer? _highlightTimer;

  @override
  void initState() {
    super.initState();
    _scrollController = widget.scrollController ?? ScrollController();
    _ownsController = widget.scrollController == null;
    _scrollController.addListener(_onScroll);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _maybeResumeCommentReport();
    });
  }

  @override
  void didUpdateWidget(covariant CommentThreadView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.highlightCommentId != widget.highlightCommentId ||
        oldWidget.highlightReplyId != widget.highlightReplyId) {
      // 新的深链目标：重置解析标记，下一帧重新翻页定位。
      _resolvedHighlightKey = null;
    }
  }

  @override
  void dispose() {
    _highlightTimer?.cancel();
    _scrollController.removeListener(_onScroll);
    if (_ownsController) {
      _scrollController.dispose();
    }
    super.dispose();
  }

  /// 当前深链目标 key：二级回复优先（reply:），否则一级评论（comment:）。
  String? get _currentHighlightKey {
    final reply = widget.highlightReplyId?.trim();
    if (reply != null && reply.isNotEmpty) return 'reply:$reply';
    final comment = widget.highlightCommentId?.trim();
    if (comment != null && comment.isNotEmpty) return 'comment:$comment';
    return null;
  }

  /// 初始列表就绪后启动深链解析：命中已加载项直接定位；否则翻页 / 展开回复
  /// 寻找目标，翻尽仍无则明确反馈，绝不静默。
  void _maybeStartHighlightResolution(CommentState state) {
    final key = _currentHighlightKey;
    if (key == null) return;
    if (_resolvedHighlightKey == key || _highlightResolutionInFlight) return;
    final ready =
        state.comments.isNotEmpty || state.status == CommentListStatus.error;
    if (!ready || state.isLoading) return;
    _highlightResolutionInFlight = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        _highlightResolutionInFlight = false;
        return;
      }
      unawaited(_resolveHighlight(key));
    });
  }

  Future<void> _resolveHighlight(String key) async {
    try {
      final replyTarget = widget.highlightReplyId?.trim();
      final commentTarget = widget.highlightCommentId?.trim();
      if (replyTarget != null && replyTarget.isNotEmpty) {
        await _resolveReplyHighlight(
          replyId: replyTarget,
          parentId: commentTarget,
          key: key,
        );
      } else if (commentTarget != null && commentTarget.isNotEmpty) {
        await _resolveCommentHighlight(commentId: commentTarget, key: key);
      }
    } finally {
      _highlightResolutionInFlight = false;
    }
  }

  /// 一级评论：当前页未命中且仍有下一页时循环翻页查找，命中即定位高亮。
  Future<void> _resolveCommentHighlight({
    required String commentId,
    required String key,
  }) async {
    for (var scanned = 0; scanned < _maxDeepLinkPageScan; scanned++) {
      if (!mounted) return;
      final state = ref.read(commentProviderFamily(widget.postId));
      final index = state.comments.indexWhere((c) => c.id == commentId);
      if (index >= 0) {
        await _completeCommentHit(commentId, index, state.comments.length, key);
        return;
      }
      if (!state.hasMore) break;
      final lengthBefore = state.comments.length;
      await ref.read(commentProviderFamily(widget.postId).notifier).loadMore();
      if (!mounted) return;
      final after = ref.read(commentProviderFamily(widget.postId));
      if (after.appendFailure != null) break;
      if (after.comments.length == lengthBefore && after.hasMore) {
        // 可能与滚动触发的翻页竞争：让出一帧再重试，避免空转。
        await WidgetsBinding.instance.endOfFrame;
      }
    }
    _reportHighlightMiss(commentId, key);
  }

  /// 二级回复：父未加载先翻主列表加载父，再展开父的回复分页直到命中目标回复。
  Future<void> _resolveReplyHighlight({
    required String replyId,
    required String? parentId,
    required String key,
  }) async {
    for (var scanned = 0; scanned < _maxDeepLinkPageScan; scanned++) {
      if (!mounted) return;
      final state = ref.read(commentProviderFamily(widget.postId));
      final located = _locateReply(state, replyId: replyId, parentId: parentId);
      if (located.reply != null) {
        await _completeReplyHit(replyId, key);
        return;
      }
      final parent = located.parent;
      if (parent != null) {
        // 父已加载但回复未在已加载分页：展开下一页回复；翻尽仍无则视为未命中。
        if (parent.replyNextCursor == null) break;
        final ok = await _safeExpandReplies(parent.id);
        if (!mounted) return;
        if (!ok) break;
        continue;
      }
      // 父未加载：翻主列表寻找父评论。
      if (!state.hasMore) break;
      final lengthBefore = state.comments.length;
      await ref.read(commentProviderFamily(widget.postId).notifier).loadMore();
      if (!mounted) return;
      final after = ref.read(commentProviderFamily(widget.postId));
      if (after.appendFailure != null) break;
      if (after.comments.length == lengthBefore && after.hasMore) {
        await WidgetsBinding.instance.endOfFrame;
      }
    }
    _reportHighlightMiss(replyId, key);
  }

  ({CommentViewData? parent, CommentViewData? reply}) _locateReply(
    CommentState state, {
    required String replyId,
    required String? parentId,
  }) {
    CommentViewData? parent;
    for (final comment in state.comments) {
      for (final item in comment.replyPreview) {
        if (item.id == replyId) {
          return (parent: comment, reply: item);
        }
      }
      if (parentId != null && parentId.isNotEmpty && comment.id == parentId) {
        parent = comment;
      }
    }
    return (parent: parent, reply: null);
  }

  Future<bool> _safeExpandReplies(String parentId) async {
    try {
      await ref
          .read(commentProviderFamily(widget.postId).notifier)
          .expandReplies(parentId);
      return true;
    } catch (error, stackTrace) {
      // 展开回复失败：交由调用方按「未命中」反馈处理，不静默吞异常。
      FlutterError.reportError(
        FlutterErrorDetails(
          exception: error,
          stack: stackTrace,
          library: 'comment_thread_view',
          context: ErrorDescription('深链展开二级回复失败'),
        ),
      );
      return false;
    }
  }

  Future<void> _completeCommentHit(
    String commentId,
    int index,
    int total,
    String key,
  ) async {
    _resolvedHighlightKey = key;
    ref
        .read(commentObservabilityProvider)
        .trackAction(
          eventName: CommentEventNames.deeplinkOpened,
          postId: widget.postId,
          commentId: commentId,
          entrySource: 'deeplink-highlight',
          result: 'hit',
        );
    if (!mounted) return;
    await _scrollToComment(commentId, index, total);
    if (!mounted) return;
    setState(() => _highlightedCommentId = commentId);
    _scheduleHighlightFadeOut();
  }

  Future<void> _completeReplyHit(String replyId, String key) async {
    _resolvedHighlightKey = key;
    ref
        .read(commentObservabilityProvider)
        .trackAction(
          eventName: CommentEventNames.deeplinkOpened,
          postId: widget.postId,
          commentId: replyId,
          entrySource: 'deeplink-highlight',
          result: 'hit',
        );
    if (!mounted) return;
    // 等待展开后的回复完成 build（其 GlobalKey 才挂载），再滚动定位。
    await WidgetsBinding.instance.endOfFrame;
    if (!mounted) return;
    await _scrollToReply(replyId);
    if (!mounted) return;
    setState(() => _highlightedReplyId = replyId);
    _scheduleHighlightFadeOut();
  }

  void _scheduleHighlightFadeOut() {
    _highlightTimer?.cancel();
    _highlightTimer = Timer(const Duration(milliseconds: 2400), () {
      if (mounted) {
        setState(() {
          _highlightedCommentId = null;
          _highlightedReplyId = null;
        });
      }
    });
  }

  void _reportHighlightMiss(String targetId, String key) {
    _resolvedHighlightKey = key;
    ref
        .read(commentObservabilityProvider)
        .trackAction(
          eventName: CommentEventNames.deeplinkOpened,
          postId: widget.postId,
          commentId: targetId,
          entrySource: 'deeplink-highlight',
          result: 'miss',
        );
    if (!mounted) return;
    AppToast.show(context, ContentText.commentDeeplinkTargetMissing);
  }

  Future<void> _scrollToComment(String commentId, int index, int total) async {
    final ctx = _commentItemKeys[commentId]?.currentContext;
    if (ctx != null) {
      await Scrollable.ensureVisible(
        ctx,
        duration: const Duration(milliseconds: 320),
        alignment: 0.1,
        curve: Curves.easeOutCubic,
      );
      return;
    }
    // 目标尚未 build（懒加载列表不可见区）：先按序号估算偏移滚近，再精确定位。
    if (_scrollController.hasClients && total > 0) {
      final maxExtent = _scrollController.position.maxScrollExtent;
      final approx = (maxExtent * index / total).clamp(0.0, maxExtent);
      await _scrollController.animateTo(
        approx,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOutCubic,
      );
      await WidgetsBinding.instance.endOfFrame;
      if (!mounted) return;
      final retryCtx = _commentItemKeys[commentId]?.currentContext;
      if (retryCtx != null && retryCtx.mounted) {
        await Scrollable.ensureVisible(
          retryCtx,
          duration: const Duration(milliseconds: 240),
          alignment: 0.1,
          curve: Curves.easeOutCubic,
        );
      }
    }
  }

  Future<void> _scrollToReply(String replyId) async {
    final ctx = _replyItemKeys[replyId]?.currentContext;
    if (ctx == null) return;
    await Scrollable.ensureVisible(
      ctx,
      duration: const Duration(milliseconds: 320),
      alignment: 0.2,
      curve: Curves.easeOutCubic,
    );
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    if (_scrollController.position.pixels >=
        _scrollController.position.maxScrollExtent - AppSpacing.xl) {
      ref.read(commentProviderFamily(widget.postId).notifier).loadMore();
    }
  }

  void _maybeResumeCommentReport() {
    if (!mounted || !ref.read(authSessionControllerProvider).isAuthenticated) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final controller = ref.read(authContinuationProvider.notifier);
      final pending = controller.take<SubmitCommentReportContinuation>();
      if (pending == null) return;
      if (pending.postId != widget.postId) {
        controller.set(
          pending,
          ownerToken: 'comment-report:${pending.postId}:${pending.commentId}',
        );
        return;
      }
      unawaited(
        _submitCommentReport(
          context,
          ref,
          commentId: pending.commentId,
          reason: pending.reason,
        ),
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      previous,
      next,
    ) {
      final wasAuthenticated = previous?.isAuthenticated ?? false;
      if (!wasAuthenticated && next.isAuthenticated) {
        _maybeResumeCommentReport();
      }
    });
    final state = ref.watch(commentProviderFamily(widget.postId));
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    if (!_initialLoaded) {
      _initialLoaded = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref
            .read(commentObservabilityProvider)
            .trackAction(
              eventName: CommentEventNames.surfaceExpose,
              postId: widget.postId,
              // 线程列表恒内嵌于 CommentDetailSurface（其自带头部），无独立头部形态。
              surfaceMode: 'embedded',
            );
        ref.read(commentProviderFamily(widget.postId).notifier).loadComments();
      });
    }
    _maybeStartHighlightResolution(state);
    return Column(
      key: TestKeys.commentThreadView,
      children: [
        if (state.failure != null && state.comments.isNotEmpty)
          AppTransientErrorNotice(
            semantic: AppUserRecoveryContract.semanticFor(
              group: AppUserRecoveryGroup.reloadLater,
              category: UiErrorCategory.backgroundAction,
              scope: UiErrorScope.global,
              presentation: UiErrorPresentation.transientNotice,
            ),
            margin: EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.xs,
            ),
          ),
        if (widget.shrinkWrap)
          _buildBody(context, state, isDark)
        else
          Expanded(child: _buildBody(context, state, isDark)),
      ],
    );
  }

  Widget _buildBody(BuildContext context, CommentState state, bool isDark) {
    if (state.isLoading && state.comments.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: AppRequestFeedback.section(),
      );
    }
    if (state.status == CommentListStatus.error && state.comments.isEmpty) {
      final resolved = runtimeErrorSemantic(
        context,
        error: state.failure!,
        category: UiErrorCategory.sectionLoad,
        scope: UiErrorScope.section,
      );
      return AppSectionErrorState(
        semantic: resolved,
        onAction: (_) async {
          await ref
              .read(commentProviderFamily(widget.postId).notifier)
              .loadComments();
        },
      );
    }
    if (state.comments.isEmpty) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.xl),
        child: Center(
          child: Text(
            ContentText.noComment,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundSecondary,
              ),
            ),
          ),
        ),
      );
    }
    return ListView.builder(
      controller: widget.shrinkWrap ? null : _scrollController,
      shrinkWrap: widget.shrinkWrap,
      // ignore: deprecated_member_use
      cacheExtent: AppSpacing.commentListCacheExtent,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.md),
      physics: widget.shrinkWrap
          ? const NeverScrollableScrollPhysics()
          : const BouncingScrollPhysics(),
      itemCount:
          1 +
          state.comments.length +
          (state.status == CommentListStatus.loadingMore ||
                  state.appendFailure != null
              ? 1
              : 0),
      itemBuilder: (context, headerAwareIndex) {
        if (headerAwareIndex == 0) {
          return _CommentSortSwitcher(
            sort: state.sort,
            isDark: isDark,
            onChanged: (sort) => ref
                .read(commentProviderFamily(widget.postId).notifier)
                .changeSort(sort),
          );
        }
        final index = headerAwareIndex - 1;
        if (index >= state.comments.length) {
          if (state.appendFailure != null) {
            final resolved = runtimeErrorSemantic(
              context,
              error: state.appendFailure!,
              category: UiErrorCategory.listAppend,
              scope: UiErrorScope.section,
              presentation: UiErrorPresentation.appendFooter,
            );
            return AppListAppendErrorFooter(
              semantic: resolved,
              onAction: (_) async {
                await ref
                    .read(commentProviderFamily(widget.postId).notifier)
                    .loadMore();
              },
            );
          }
          return Padding(
            padding: EdgeInsets.all(AppSpacing.md),
            child: AppRequestFeedback.section(),
          );
        }
        final comment = state.comments[index];
        final itemKey = _commentItemKeys.putIfAbsent(
          comment.id,
          () => GlobalKey(),
        );
        return KeyedSubtree(
          key: itemKey,
          child: _CommentThreadItem(
            postId: widget.postId,
            comment: comment,
            isDark: isDark,
            highlighted: _highlightedCommentId == comment.id,
            highlightedReplyId: _highlightedReplyId,
            loadingReplies: state.loadingReplyCommentIds.contains(comment.id),
            repliesExpanded: state.expandedReplyCommentIds.contains(comment.id),
            replyPreviewCount: state.replyPreviewCount,
            foldLineCount: state.foldLineCount,
            replyItemKeyFor: (replyId) =>
                _replyItemKeys.putIfAbsent(replyId, () => GlobalKey()),
            onReplySelected: widget.onReplySelected,
          ),
        );
      },
    );
  }
}
