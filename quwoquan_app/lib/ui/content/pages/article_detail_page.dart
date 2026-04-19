// ignore_for_file: sort_child_properties_last
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/post_read_projection_facade.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class ArticleDetailPage extends ConsumerStatefulWidget {
  const ArticleDetailPage({super.key, required this.articleId});

  final String articleId;

  @override
  ConsumerState<ArticleDetailPage> createState() => _ArticleDetailPageState();
}

class _ArticleDetailPageState extends ConsumerState<ArticleDetailPage> {
  ArticleDetailView? _article;
  PostReadUiBundle? _postReadBundle;
  bool _isLoading = true;
  Object? _loadError;
  bool _isLiked = false;
  bool _isSaved = false;
  int _likesCount = 0;
  int _commentsCount = 0;
  late final DateTime _enterTime = DateTime.now();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadArticle());
  }

  @override
  void deactivate() {
    final seconds =
        DateTime.now().difference(_enterTime).inMilliseconds / 1000.0;
    if (seconds >= 1) {
      ref
          .read(behaviorRepositoryProvider)
          .reportSingle(
            contentId: widget.articleId,
            action: 'dwell',
            duration: seconds,
          );
    }
    super.deactivate();
  }

  Future<void> _loadArticle() async {
    try {
      final detail = await ref
          .read(contentRepositoryProvider)
          .getPost(postId: widget.articleId);
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
      setState(() {
        _article = article;
        _postReadBundle = readBundle;
        _likesCount = article.stats.likes;
        _commentsCount = article.stats.comments;
        _isLoading = false;
        _loadError = null;
      });
      ref
          .read(behaviorRepositoryProvider)
          .reportSingle(contentId: widget.articleId, action: 'impression');
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
                          metrics.frameSpecForStageWidth(stageWidth).paperSize.height +
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
                    icon: _isLiked
                        ? CupertinoIcons.hand_thumbsup_fill
                        : CupertinoIcons.hand_thumbsup,
                    label: _formatCount(_likesCount),
                    color: _isLiked
                        ? CupertinoColors.activeBlue.resolveFrom(context)
                        : CupertinoColors.label.resolveFrom(context),
                    onTap: () {
                      setState(() {
                        _isLiked = !_isLiked;
                        _likesCount += _isLiked ? 1 : -1;
                        if (_likesCount < 0) _likesCount = 0;
                      });
                    },
                  ),
                  _BottomAction(
                    icon: _isSaved
                        ? CupertinoIcons.bookmark_fill
                        : CupertinoIcons.bookmark,
                    label: _formatCount(article.stats.bookmarks),
                    color: _isSaved
                        ? CupertinoColors.systemYellow.resolveFrom(context)
                        : CupertinoColors.label.resolveFrom(context),
                    onTap: () => setState(() => _isSaved = !_isSaved),
                  ),
                  _BottomAction(
                    icon: CupertinoIcons.chat_bubble,
                    label: _formatCount(_commentsCount),
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
