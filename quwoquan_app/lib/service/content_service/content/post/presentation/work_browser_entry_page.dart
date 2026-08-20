import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/di/feed_session_provider.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show workBrowserContentPostDetailReaderProvider;
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_state_bridge.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/presentation/content_viewer_composition.dart';

/// 沉浸式浏览器「直达入口」。
///
/// 仅有 `workId`（分享/通知深链、评论跳原文）而无预置 [MediaViewerExtra] 时，
/// 按 id 拉取该帖并组装单帖 extra，再交给 [UnifiedMediaViewerPage] 渲染。
///
/// 修复先前断点：旧路由在缺 extra 时丢弃 `workId` 回退到发现页推荐流，直达用户
/// 看到无关内容；水合失败也仅静默埋点。此页改为「按 id 直拉 + 显式错误态」，
/// 让删除态/不存在等场景走结构化运行时错误。
class WorkBrowserEntryPage extends ConsumerStatefulWidget {
  const WorkBrowserEntryPage({
    super.key,
    required this.workId,
    this.source = 'workBrowser',
    this.referralSource = ReferralSource.deepLink,
    this.feedRequestId,
    this.sourceAppearanceMode = UiErrorAppearanceMode.inherit,
    this.commentContext = const MediaViewerCommentContext(),
  });

  final String workId;
  final String source;
  final ReferralSource referralSource;
  final String? feedRequestId;
  final UiErrorAppearanceMode sourceAppearanceMode;
  final MediaViewerCommentContext commentContext;

  @override
  ConsumerState<WorkBrowserEntryPage> createState() =>
      _WorkBrowserEntryPageState();
}

class _WorkBrowserEntryPageState extends ConsumerState<WorkBrowserEntryPage> {
  MediaViewerExtra? _extra;
  UiErrorSemantic? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _resolve());
  }

  @override
  void didUpdateWidget(WorkBrowserEntryPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workId.trim() == widget.workId.trim()) {
      return;
    }
    // 同一路由换 workId 时 State 被复用：必须先丢弃上一个 extra 回到加载态，
    // 否则直达用户会继续看到上一个作品——正是本页要消除的「看到无关内容」断点。
    _extra = null;
    _error = null;
    _loading = true;
    WidgetsBinding.instance.addPostFrameCallback((_) => _resolve());
  }

  Future<void> _resolve() async {
    if (!mounted) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    final workId = widget.workId.trim();
    if (workId.isEmpty) {
      _applyError(Exception('empty workId'));
      return;
    }
    try {
      final detail = await ref
          .read(workBrowserContentPostDetailReaderProvider)
          .getPost(postId: workId);
      if (!mounted) {
        return;
      }
      applyConfirmedInteractionPost(ref, detail.post);
      final inheritedFeedRequestId = (widget.feedRequestId ?? '').trim();
      final feedRequestId = inheritedFeedRequestId.isNotEmpty
          ? inheritedFeedRequestId
          : ref.read(feedSessionProvider.notifier).newFeedRequestId();
      final extra = ContentViewerComposition.singlePostExtra(
        ref,
        detail: detail,
        source: widget.source,
        referralSource: widget.referralSource,
        feedRequestId: feedRequestId,
        commentContext: widget.commentContext,
      );
      primeMediaViewerInteractionSnapshot(ref, extra.interactionSnapshot);
      if (!mounted) {
        return;
      }
      setState(() {
        _extra = extra;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      _applyError(error);
    }
  }

  void _applyError(Object error) {
    final semantic = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
    setState(() {
      _error = semantic.withSurfaceContext(
        appearanceMode: widget.sourceAppearanceMode,
        sourceRouteId: 'workBrowser',
        sourceSurfaceId: widget.source,
      );
      _loading = false;
    });
  }

  void _back() {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutePaths.home);
    }
  }

  @override
  Widget build(BuildContext context) {
    final extra = _extra;
    if (extra != null) {
      return ContentViewerComposition.unifiedMediaViewer(extra);
    }
    final showError = !_loading && _error != null;
    return _withSourceAppearance(
      context,
      Builder(
        builder: (themedContext) {
          return CupertinoPageScaffold(
            backgroundColor: showError || _loading
                ? AppColors.iosSystemBackground(themedContext)
                : AppColors.black,
            child: SafeArea(
              child: _loading
                  ? Center(
                      key: const ValueKey('work-browser-entry-loading'),
                      child: AppRequestFeedback.inline(
                        indicatorColor: AppColors.iosLabel(themedContext),
                      ),
                    )
                  : Stack(
                      children: <Widget>[
                        AppPageErrorState(
                          key: const ValueKey('work-browser-entry-error'),
                          semantic: ensureRetryUiErrorSemantic(_error!),
                          onRecovery: (action) async {
                            if (action.type == UiErrorActionType.retry ||
                                action.type == UiErrorActionType.resubmit) {
                              await _resolve();
                              return _error == null
                                  ? UiRecoveryOutcome.recovered
                                  : UiRecoveryOutcome.stillBlocked;
                            } else if (action.type ==
                                UiErrorActionType.dismiss) {
                              _back();
                              return UiRecoveryOutcome.handedOff;
                            }
                            return UiRecoveryOutcome.cancelled;
                          },
                        ),
                        Align(
                          alignment: AlignmentDirectional.topStart,
                          child: AppNavigationBarIconButton(
                            key: const ValueKey<String>(
                              'work-browser-entry-error-back',
                            ),
                            icon: CupertinoIcons.back,
                            onPressed: _back,
                          ),
                        ),
                      ],
                    ),
            ),
          );
        },
      ),
    );
  }

  Widget _withSourceAppearance(BuildContext context, Widget child) {
    final brightness = widget.sourceAppearanceMode.brightness;
    if (brightness == null) {
      return child;
    }
    return CupertinoTheme(
      data: CupertinoTheme.of(context).copyWith(brightness: brightness),
      child: child,
    );
  }
}
