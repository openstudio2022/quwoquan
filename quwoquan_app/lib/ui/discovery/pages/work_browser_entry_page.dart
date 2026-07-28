import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/interactions/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/discovery/pages/unified_media_viewer_page.dart';
import 'package:quwoquan_app/ui/content/services/single_post_media_viewer.dart';

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
      final extra = buildSinglePostMediaViewerExtra(
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
      return UnifiedMediaViewerPage(extra: extra);
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
                          onAction: (action) async {
                            if (action.type == UiErrorActionType.retry ||
                                action.type == UiErrorActionType.resubmit) {
                              await _resolve();
                            } else if (action.type ==
                                UiErrorActionType.dismiss) {
                              _back();
                            }
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
