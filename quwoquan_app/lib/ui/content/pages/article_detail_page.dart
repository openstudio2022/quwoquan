// ignore_for_file: sort_child_properties_last
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/content_engagement_tracker.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/post_read_projection_facade.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class ArticleDetailPage extends ConsumerStatefulWidget {
  const ArticleDetailPage({
    super.key,
    required this.articleId,
    this.referralSource = ReferralSource.organicFeed,
    this.feedRequestId,
  });

  final String articleId;
  final ReferralSource referralSource;
  final String? feedRequestId;

  @override
  ConsumerState<ArticleDetailPage> createState() => _ArticleDetailPageState();
}

class _ArticleDetailPageState extends ConsumerState<ArticleDetailPage> {
  ArticleDetailView? _article;
  PostReadUiBundle? _postReadBundle;
  bool _isLoading = true;
  Object? _loadError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadArticle());
  }

  @override
  void deactivate() {
    ref.read(contentEngagementTrackerProvider).trackContentExit(widget.articleId);
    super.deactivate();
  }

  Future<void> _loadArticle() async {
    try {
      final detail = await ref
          .read(contentRepositoryProvider)
          .getPost(postId: widget.articleId);
      applyConfirmedInteractionPost(ref, detail.post);
      final article = projectArticleDetailViewFromPayload(
        detail,
        fallbackArticleId: widget.articleId,
      );
      final readBundle = PostReadUiBundle.fromPost(
        detail.post,
        PostReadSurfaceId.detailArticle,
        wire: detail.mergedArticleWireMap,
      );
      if (!mounted) return;
      final snapshot = buildMediaViewerInteractionSnapshot(
        posts: <PostBaseDto>[detail.post],
        discoveryState: ref.read(discoveryStateProvider),
        relationshipState: ref.read(userRelationshipStateProvider),
        postInteractionState: ref.read(postInteractionStateProvider),
      );
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        primeMediaViewerInteractionSnapshot(ref, snapshot);
      });
      setState(() {
        _article = article;
        _postReadBundle = readBundle;
        _isLoading = false;
        _loadError = null;
      });
      ref.read(contentEngagementTrackerProvider).trackContentEnter(
        widget.articleId,
        contentType: ContentType.article,
        referralSource: widget.referralSource,
        authorId: detail.post.authorId,
        totalPages: article.pages.length,
        feedRequestId: widget.feedRequestId,
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _postReadBundle = null;
        _isLoading = false;
        _loadError = e;
      });
    }
  }

  void _openAssistantHalfSheet() {
    final target = VisitTarget.page('article');
    final service = ref.read(visitRecorderServiceProvider);
    final ctx = AssistantOpenContext(
      source: AssistantSource.article,
      visitTarget: target,
      experienceLevel: service.getExperience(target),
    );
    AssistantHalfSheet.show(context, ctx);
  }

  String _formatCount(int n) {
    return formatCompactActionCount(n);
  }

  String _formatArticleDate(String rawValue) {
    final date = DateTime.tryParse(rawValue);
    if (date == null) {
      return rawValue;
    }
    return '${date.year}年${context.l10n.monthDayTemplate(date.month, date.day)}';
  }

  @override
  Widget build(BuildContext context) {
    ref.watch(postInteractionStateProvider);
    final background = CupertinoColors.systemGroupedBackground.resolveFrom(
      context,
    );
    final navBackground = CupertinoColors.systemBackground
        .resolveFrom(context)
        .withValues(alpha: 0.92);

    if (_isLoading) {
      return AppScaffold(
        backgroundColor: background,
        child: const Center(child: CupertinoActivityIndicator()),
      );
    }

    if (_article == null) {
      return AppScaffold(
        backgroundColor: background,
        navigationBar: AppNavigationBar(
          backgroundColor: AppColors.transparent,
          leading: AppNavigationBarIconButton(
            icon: CupertinoIcons.back,
            onPressed: () => context.canPop()
                ? context.pop()
                : context.go(AppRoutePaths.home),
          ),
        ),
        child: Center(
          child: Text(
            _loadError?.toString() ?? context.l10n.articleNotFound,
            style: TextStyle(
              color: CupertinoColors.secondaryLabel.resolveFrom(context),
              fontSize: AppTypography.base,
            ),
          ),
        ),
      );
    }

    final article = _article!;
    final postId = widget.articleId;
    final isLiked = effectivePostLiked(ref, postId);
    final isSaved = effectivePostSaved(ref, postId);
    final likesCount = effectivePostLikeCount(
      ref,
      postId,
      fallback: article.stats.likes,
    );
    final commentsCount = effectivePostCommentCount(
      ref,
      postId,
      fallback: article.stats.comments,
    );
    final bookmarksCount = effectivePostBookmarkCount(
      ref,
      postId,
      fallback: article.stats.bookmarks,
    );
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      backgroundColor: background,
      navigationBar: AppNavigationBar(
        backgroundColor: navBackground,
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () =>
              context.canPop() ? context.pop() : context.go(AppRoutePaths.home),
        ),
        middle: Text(
          article.title.trim().isNotEmpty
              ? article.title
              : (_postReadBundle?.presentation.title ?? ''),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        trailing: AppNavigationBarIconButton(
          icon: Icons.auto_awesome,
          onPressed: _openAssistantHalfSheet,
        ),
      ),
      child: Column(
        children: [
          Expanded(
            child: NotificationListener<ScrollNotification>(
              onNotification: (notification) {
                if (notification is ScrollUpdateNotification &&
                    notification.metrics.maxScrollExtent > 0) {
                  final depth = notification.metrics.pixels /
                      notification.metrics.maxScrollExtent;
                  ref.read(contentEngagementTrackerProvider).trackContentProgress(
                    widget.articleId,
                    scrollDepth: depth.clamp(0.0, 1.0),
                  );
                }
                return false;
              },
              child: SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.containerMd,
                AppSpacing.containerMd,
                AppSpacing.containerLg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _ArticleHeader(
                    article: article,
                    dateText: _formatArticleDate(article.date),
                  ),
                  SizedBox(height: AppSpacing.interGroupMd),
                  _ArticleSectionLabel(label: context.l10n.articleContent),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  LayoutBuilder(
                    builder: (context, constraints) {
                      final pages = resolvePaginatedArticlePages(
                        context: context,
                        constraints: constraints,
                        document: article.document,
                        template: article.template,
                        fontPreset: article.fontPreset,
                        fallbackPages: article.pages,
                        variant: ArticleCanvasVariant.detail,
                      );
                      final metrics = resolveArticleCanvasMetrics(
                        context,
                        constraints,
                        variant: ArticleCanvasVariant.detail,
                      );
                      final pagePadding = articleReaderStagePagePadding();
                      final stageWidth = resolveArticlePaperStageWidth(
                        context,
                        constraints,
                        stagePadding: pagePadding,
                        allowLandscapeSpread: true,
                      );
                      final stageHeight =
                          metrics
                              .frameSpecForStageWidth(stageWidth)
                              .paperSize
                              .height +
                          pagePadding.vertical;
                      return UnconstrainedBox(
                        alignment: Alignment.topCenter,
                        child: SizedBox(
                          width: stageWidth,
                          height: stageHeight,
                          child: ArticleReadOnlyBookDeck(
                            pages: pages,
                            template: article.template,
                            fontPreset: article.fontPreset,
                            metrics: metrics,
                            coverUrl: article.coverImage,
                            pagePadding: pagePadding,
                          ),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
            ),
          ),
          Container(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
            ),
            decoration: BoxDecoration(
              color: CupertinoColors.systemBackground
                  .resolveFrom(context)
                  .withValues(alpha: 0.96),
              border: Border(
                top: BorderSide(
                  color: CupertinoColors.separator.resolveFrom(context),
                ),
              ),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _BottomAction(
                    icon: isLiked
                        ? CupertinoIcons.hand_thumbsup_fill
                        : CupertinoIcons.hand_thumbsup,
                    label: _formatCount(likesCount),
                    color: isLiked
                        ? CupertinoColors.activeBlue.resolveFrom(context)
                        : CupertinoColors.label.resolveFrom(context),
                    onTap: () {
                      syncPostLikeIntent(
                        ref,
                        postId: postId,
                        isLiked: !isLiked,
                        likeCount: isLiked
                            ? (likesCount - 1).clamp(0, 1 << 31).toInt()
                            : likesCount + 1,
                      );
                    },
                  ),
                  _BottomAction(
                    icon: isSaved
                        ? CupertinoIcons.bookmark_fill
                        : CupertinoIcons.bookmark,
                    label: _formatCount(bookmarksCount),
                    color: isSaved
                        ? CupertinoColors.systemYellow.resolveFrom(context)
                        : CupertinoColors.label.resolveFrom(context),
                    onTap: () {
                      syncPostSaveIntent(
                        ref,
                        postId: postId,
                        isSaved: !isSaved,
                        bookmarkCount: isSaved
                            ? (bookmarksCount - 1).clamp(0, 1 << 31).toInt()
                            : bookmarksCount + 1,
                      );
                    },
                  ),
                  _BottomAction(
                    icon: CupertinoIcons.chat_bubble,
                    label: _formatCount(commentsCount),
                    color: CupertinoColors.label.resolveFrom(context),
                    onTap: () {
                      CommentViewer.showModal(
                        context: context,
                        postId: widget.articleId,
                      );
                    },
                  ),
                  _BottomAction(
                    icon: CupertinoIcons.arrowshape_turn_up_right,
                    label: context.l10n.share,
                    color: CupertinoColors.label.resolveFrom(context),
                    onTap: () {},
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ArticleHeader extends StatelessWidget {
  const _ArticleHeader({required this.article, required this.dateText});

  final ArticleDetailView article;
  final String dateText;

  @override
  Widget build(BuildContext context) {
    final panelColor = CupertinoColors.secondarySystemGroupedBackground
        .resolveFrom(context);
    final titleColor = CupertinoColors.label.resolveFrom(context);
    final bodyColor = CupertinoColors.secondaryLabel.resolveFrom(context);
    final stats = <String>[
      '${formatCompactActionCount(article.stats.likes)} 赞',
      '${formatCompactActionCount(article.stats.comments)} 评论',
      '${formatCompactActionCount(article.stats.bookmarks)} 收藏',
    ];

    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: panelColor,
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (article.coverImage.isNotEmpty) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              child: AspectRatio(
                aspectRatio: 16 / 10,
                child: ArticleAdaptiveImage(imageUrl: article.coverImage),
              ),
            ),
            SizedBox(height: AppSpacing.interGroupMd),
          ],
          Text(
            article.title,
            style: TextStyle(
              color: titleColor,
              fontSize: AppTypography.xxl,
              fontWeight: AppTypography.bold,
              height: 1.35, // ignore: verify_dart_semantic
            ),
          ),
          if (article.description.trim().isNotEmpty) ...[
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              article.description,
              style: TextStyle(
                color: bodyColor,
                fontSize: AppTypography.base,
                height: 1.75, // ignore: verify_dart_semantic
              ),
            ),
          ],
          SizedBox(height: AppSpacing.interGroupMd),
          Row(
            children: [
              _ArticleAvatar(imageUrl: article.author.avatar),
              SizedBox(width: AppSpacing.intraGroupSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            article.author.name.trim().isEmpty
                                ? context.l10n.anonymous
                                : article.author.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: titleColor,
                              fontSize: AppTypography.base,
                              fontWeight: AppTypography.semiBold,
                            ),
                          ),
                        ),
                        if ((article.author.badge ?? '').isNotEmpty) ...[
                          SizedBox(width: AppSpacing.intraGroupXs),
                          _ArticleBadge(label: article.author.badge!),
                        ],
                      ],
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      dateText,
                      style: TextStyle(
                        color: bodyColor,
                        fontSize: AppTypography.sm,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Wrap(
            spacing: AppSpacing.intraGroupXs,
            runSpacing: AppSpacing.intraGroupXs,
            children: stats
                .map((text) => _ArticleStatChip(label: text))
                .toList(),
          ),
        ],
      ),
    );
  }
}

class _ArticleSectionLabel extends StatelessWidget {
  const _ArticleSectionLabel({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: TextStyle(
        color: CupertinoColors.secondaryLabel.resolveFrom(context),
        fontSize: AppTypography.sm,
        fontWeight: AppTypography.semiBold,
      ),
    );
  }
}

class _ArticleAvatar extends StatelessWidget {
  const _ArticleAvatar({required this.imageUrl});

  final String imageUrl;

  @override
  Widget build(BuildContext context) {
    return ClipOval(
      child: SizedBox(
        width: AppSpacing.avatarUserMd,
        height: AppSpacing.avatarUserMd,
        child: ArticleAdaptiveImage(imageUrl: imageUrl),
      ),
    );
  }
}

class _ArticleBadge extends StatelessWidget {
  const _ArticleBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupXs,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: CupertinoColors.activeBlue
            .resolveFrom(context)
            .withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: CupertinoColors.activeBlue.resolveFrom(context),
          fontSize: AppTypography.xs,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}

class _ArticleStatChip extends StatelessWidget {
  const _ArticleStatChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: CupertinoColors.systemGrey6.resolveFrom(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: CupertinoColors.secondaryLabel.resolveFrom(context),
          fontSize: AppTypography.sm,
          fontWeight: AppTypography.medium,
        ),
      ),
    );
  }
}

class _BottomAction extends StatelessWidget {
  const _BottomAction({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        width: AppSpacing.largeButtonSize,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: AppSpacing.iconMedium),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: CupertinoColors.secondaryLabel.resolveFrom(context),
                fontSize: AppTypography.xs,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
