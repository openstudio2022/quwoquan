// ignore_for_file: sort_child_properties_last
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/ui/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';

class ArticleDetailPage extends ConsumerStatefulWidget {
  const ArticleDetailPage({super.key, required this.articleId});

  final String articleId;

  @override
  ConsumerState<ArticleDetailPage> createState() => _ArticleDetailPageState();
}

class _ArticleDetailPageState extends ConsumerState<ArticleDetailPage> {
  late final PageController _cardController;
  ArticleDetailView? _article;
  bool _isLoading = true;
  Object? _loadError;
  int _currentCardPage = 0;
  bool _isLiked = false;
  bool _isSaved = false;
  int _likesCount = 0;
  int _commentsCount = 0;
  late final DateTime _enterTime = DateTime.now();

  @override
  void initState() {
    super.initState();
    _cardController = PageController();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadArticle());
  }

  @override
  void dispose() {
    _cardController.dispose();
    super.dispose();
  }

  @override
  void deactivate() {
    final seconds = DateTime.now().difference(_enterTime).inMilliseconds / 1000.0;
    if (seconds >= 1) {
      ref.read(behaviorRepositoryProvider).reportSingle(
            contentId: widget.articleId,
            action: 'dwell',
            duration: seconds,
          );
    }
    super.deactivate();
  }

  Future<void> _loadArticle() async {
    try {
      final dataService = ref.read(dataServiceProvider);
      final raw = await dataService.getDataItem(
        endpoint: '/posts',
        id: widget.articleId,
      );
      final article = projectArticleDetailView(
        raw,
        fallbackArticleId: widget.articleId,
      );
      if (!mounted) return;
      setState(() {
        _article = article;
        _likesCount = article.stats.likes;
        _commentsCount = article.stats.comments;
        _isLoading = false;
        _loadError = null;
      });
      ref.read(behaviorRepositoryProvider).reportSingle(
            contentId: widget.articleId,
            action: 'impression',
          );
    } catch (e) {
      if (!mounted) return;
      setState(() {
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
    if (n >= 100000) return '10万+';
    return '$n';
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return AppScaffold(
        backgroundColor: AppColors.worksBackground,
        child: const Center(child: CupertinoActivityIndicator()),
      );
    }

    if (_article == null) {
      return AppScaffold(
        backgroundColor: AppColors.worksBackground,
        navigationBar: AppNavigationBar(
          backgroundColor: Colors.transparent,
          leading: CupertinoButton(
            padding: EdgeInsets.zero,
            child: const Icon(CupertinoIcons.back, color: AppColors.worksTitle),
            onPressed: () => context.canPop()
                ? context.pop()
                : context.go(AppRoutePaths.home),
          ),
        ),
        child: Center(
          child: Text(
            _loadError?.toString() ?? '文章不存在',
            style: TextStyle(
              color: AppColors.worksBodyText,
              fontSize: AppTypography.base,
            ),
          ),
        ),
      );
    }

    final article = _article!;
    final pages = <Widget>[
      _ArticlePosterPage(article: article),
      ...article.cards.map((card) => _ArticleCardPage(card: card)),
    ];
    final cardTotal = pages.length;
    final cardCurrent = (_currentCardPage + 1).clamp(1, cardTotal);

    return AppScaffold(
      backgroundColor: AppColors.worksBackground,
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.worksBackground.withValues(alpha: 0.92),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          child: Icon(CupertinoIcons.back, color: AppColors.worksTitle),
          onPressed: () => context.canPop()
              ? context.pop()
              : context.go(AppRoutePaths.home),
        ),
        middle: Text(
          article.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            color: AppColors.worksTitle,
            fontSize: AppTypography.base,
            fontWeight: AppTypography.semiBold,
          ),
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CupertinoButton(
              padding: EdgeInsets.zero,
              child: Icon(Icons.auto_awesome, color: AppColors.worksTitle),
              onPressed: _openAssistantHalfSheet,
            ),
            Padding(
              padding: EdgeInsets.only(right: AppSpacing.containerSm),
              child: Center(
                child: Text(
                  '$cardCurrent/$cardTotal',
                  style: TextStyle(
                    color: AppColors.worksBodyText,
                    fontSize: AppTypography.sm,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
      child: Column(
        children: [
          Expanded(
            child: PageView.builder(
              controller: _cardController,
              onPageChanged: (index) => setState(() => _currentCardPage = index),
              itemCount: pages.length,
              itemBuilder: (context, index) => pages[index],
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
              color: AppColors.worksBackground.withValues(alpha: 0.95),
              border: Border(
                top: BorderSide(
                  color: AppColors.worksBodyText.withValues(alpha: 0.12),
                ),
              ),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  _BottomAction(
                    icon: _isLiked
                        ? CupertinoIcons.hand_thumbsup_fill
                        : CupertinoIcons.hand_thumbsup,
                    label: _formatCount(_likesCount),
                    color: _isLiked ? AppColors.worksAccent : AppColors.worksTitle,
                    onTap: () {
                      setState(() {
                        _isLiked = !_isLiked;
                        _likesCount += _isLiked ? 1 : -1;
                        if (_likesCount < 0) _likesCount = 0;
                      });
                    },
                  ),
                  _BottomAction(
                    icon: CupertinoIcons.arrowshape_turn_up_right,
                    label: _formatCount(article.stats.bookmarks),
                    color: AppColors.worksTitle,
                    onTap: () {},
                  ),
                  _BottomAction(
                    icon: _isSaved ? CupertinoIcons.bookmark_fill : CupertinoIcons.bookmark,
                    label: _isSaved ? UITextConstants.following : UITextConstants.follow,
                    color: _isSaved ? AppColors.warning : AppColors.worksTitle,
                    onTap: () => setState(() => _isSaved = !_isSaved),
                  ),
                  _BottomAction(
                    icon: CupertinoIcons.chat_bubble,
                    label: _formatCount(_commentsCount),
                    color: AppColors.worksTitle,
                    onTap: () {
                      CommentViewer.showModal(
                        context: context,
                        postId: widget.articleId,
                      );
                    },
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

class _ArticlePosterPage extends StatelessWidget {
  const _ArticlePosterPage({required this.article});

  final ArticleDetailView article;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        if (article.coverImage.isNotEmpty)
          CachedNetworkImage(
            imageUrl: article.coverImage,
            fit: BoxFit.cover,
            placeholder: (context, url) => Container(color: AppColors.worksBackground),
            errorWidget: (context, url, error) => Container(color: AppColors.worksBackground),
          )
        else
          Container(color: AppColors.worksBackground),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.black.withValues(alpha: 0.16),
                  Colors.black.withValues(alpha: 0.36),
                  AppColors.worksBackground.withValues(alpha: 0.92),
                ],
              ),
            ),
          ),
        ),
        Positioned(
          left: AppSpacing.containerLg,
          right: AppSpacing.containerLg,
          bottom: AppSpacing.containerLg,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                article.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.worksTitle,
                  fontSize: AppTypography.xxl,
                  fontWeight: AppTypography.bold,
                  height: 1.35, // ignore: verify_dart_semantic
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupSm),
              Text(
                article.description,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: AppColors.worksBodyText,
                  fontSize: AppTypography.base,
                  height: 1.8, // ignore: verify_dart_semantic
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ArticleCardPage extends StatelessWidget {
  const _ArticleCardPage({required this.card});

  final ArticleCardView card;

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final imageWidth = switch (card.layout) {
      'third' => width / 3,
      'half' => width / 2,
      _ => width,
    };
    final imageHeight = imageWidth * (9 / 16);

    Widget imageBlock() {
      if (card.imageUrl == null || card.imageUrl!.isEmpty) {
        return const SizedBox.shrink();
      }
      return SizedBox(
        width: imageWidth,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              child: SizedBox(
                width: imageWidth,
                height: imageHeight,
                child: CachedNetworkImage(
                  imageUrl: card.imageUrl!,
                  fit: BoxFit.cover,
                  placeholder: (context, url) => Container(
                    color: AppColors.worksDrawerBg,
                  ),
                  errorWidget: (context, url, error) => Container(
                    color: AppColors.worksDrawerBg,
                  ),
                ),
              ),
            ),
            if ((card.caption ?? '').isNotEmpty) ...[
              SizedBox(height: AppSpacing.intraGroupXs),
              Text(
                card.caption!,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  color: AppColors.worksCaption,
                ),
              ),
            ],
          ],
        ),
      );
    }

    return Container(
      color: AppColors.worksBackground,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerLg,
        AppSpacing.containerLg,
        AppSpacing.containerLg,
        AppSpacing.containerMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (card.title.isNotEmpty)
            Text(
              card.title,
              style: TextStyle(
                color: AppColors.worksTitle,
                fontSize: AppTypography.xl,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          if (card.title.isNotEmpty) SizedBox(height: AppSpacing.intraGroupSm),
          if (card.layout == 'full') ...[
            imageBlock(),
            if ((card.imageUrl ?? '').isNotEmpty) SizedBox(height: AppSpacing.interGroupSm),
            Expanded(
              child: SingleChildScrollView(
                child: Text(
                  card.body,
                  style: TextStyle(
                    color: AppColors.worksBodyText,
                    fontSize: AppTypography.base,
                    height: 2.0, // ignore: verify_dart_semantic
                  ),
                ),
              ),
            ),
          ] else
            Expanded(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  imageBlock(),
                  if ((card.imageUrl ?? '').isNotEmpty)
                    SizedBox(width: AppSpacing.interGroupSm),
                  Expanded(
                    child: SingleChildScrollView(
                      child: Text(
                        card.body,
                        style: TextStyle(
                          color: AppColors.worksBodyText,
                          fontSize: AppTypography.base,
                          height: 2.0, // ignore: verify_dart_semantic
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
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
      child: Container(
        margin: EdgeInsets.only(left: AppSpacing.intraGroupMd),
        width: AppSpacing.iconButtonMinSizeSm,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: AppSpacing.iconMedium),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              label,
              style: TextStyle(
                color: AppColors.worksBodyText,
                fontSize: AppTypography.xs,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
