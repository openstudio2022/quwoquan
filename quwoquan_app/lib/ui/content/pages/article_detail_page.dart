// ignore_for_file: unnecessary_underscores

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/assistant/context/assistant_open_context.dart';
import 'package:quwoquan_app/features/assistant/widgets/assistant_half_sheet.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';

/// 文章详情页 - 1:1 对应 ArticleDetailView.tsx → UniversalArticleLayout
/// 含：顶栏（返回/吸顶标题）、封面、标题、作者行、正文、底栏（点赞/评论/收藏/分享）、评论区
class ArticleDetailPage extends ConsumerStatefulWidget {
  const ArticleDetailPage({
    super.key,
    required this.articleId,
  });

  final String articleId;

  @override
  ConsumerState<ArticleDetailPage> createState() => _ArticleDetailPageState();
}

class _ArticleDetailPageState extends ConsumerState<ArticleDetailPage> {
  ArticleDetailView? _article;
  bool _isLoading = true;
  Object? _loadError;
  bool _isLiked = false;
  bool _isSaved = false;
  bool _isFollowing = false;
  int _likesCount = 0;
  int _commentsCount = 0;
  late final DateTime _enterTime = DateTime.now();

  void _reportDwell() {
    final seconds = DateTime.now().difference(_enterTime).inMilliseconds / 1000.0;
    if (seconds < 1) return;
    ref.read(behaviorRepositoryProvider).reportSingle(
      contentId: widget.articleId,
      action: 'dwell',
      duration: seconds,
    );
  }

  @override
  void deactivate() {
    _reportDwell();
    super.deactivate();
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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadArticle();
    });
  }

  Future<void> _loadArticle() async {
    try {
      final dataService = ref.read(dataServiceProvider);
      final post = await dataService.getDataItem(
        endpoint: '/posts',
        id: widget.articleId,
      );
      final article = projectArticleDetailView(post, fallbackArticleId: widget.articleId);
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

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final bgColor = AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final fgColor = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final contentBg = isDark ? const Color(0xFF0A0A0A) : Colors.white;
    final contentText = fgColor;

    if (_isLoading) {
      return Scaffold(
        backgroundColor: bgColor,
        appBar: AppBar(
          backgroundColor: bgColor,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/');
              }
            },
          ),
          title: Text(context.l10n.discoveryTabArticle, style: TextStyle(color: fgColor)),
        ),
        body: const Center(
          child: CircularProgressIndicator(),
        ),
      );
    }

    if (_article == null) {
      return Scaffold(
        backgroundColor: bgColor,
        appBar: AppBar(
          backgroundColor: bgColor,
          leading: IconButton(
            icon: const Icon(Icons.arrow_back),
            onPressed: () {
              if (context.canPop()) {
                context.pop();
              } else {
                context.go('/');
              }
            },
          ),
          title: Text(context.l10n.discoveryTabArticle, style: TextStyle(color: fgColor)),
        ),
        body: Center(
          child: Text(
            _loadError == null ? context.l10n.articleNotFound : _loadError.toString(),
            style: TextStyle(color: AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary)),
          ),
        ),
      );
    }

    final article = _article!;
    final author = article.author;
    final authorName = author.name;
    final hasCarousel = article.layoutMode == 'carousel' &&
        article.images.length > 1;

    return Scaffold(
      backgroundColor: contentBg,
      appBar: AppBar(
        backgroundColor: contentBg.withValues(alpha: 0.95),
        elevation: 0,
        scrolledUnderElevation: 1,
        leading: IconButton(
          icon: Icon(Icons.arrow_back, color: contentText),
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go('/');
            }
          },
        ),
        title: Text(
          article.title.isNotEmpty ? article.title : context.l10n.discoveryTabArticle,
          style: TextStyle(
            color: contentText,
            fontSize: 16.sp,
            fontWeight: FontWeight.w700,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        actions: [
          IconButton(
            icon: Icon(Icons.auto_awesome, color: contentText),
            onPressed: _openAssistantHalfSheet,
            tooltip: AppConceptConstants.assistantLabel,
          ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 封面区：hero 单图 或 carousel 多图
                  if (article.coverImage.isNotEmpty || article.images.isNotEmpty) ...[
                    if (hasCarousel)
                      SizedBox(
                        height: 200.h,
                        child: PageView.builder(
                          itemCount: article.images.length,
                          itemBuilder: (context, i) {
                            return _coverImage(article.images[i]);
                          },
                        ),
                      )
                    else
                      AspectRatio(
                        aspectRatio: 16 / 9,
                        child: _coverImage(
                          article.coverImage.isNotEmpty
                              ? article.coverImage
                              : (article.images.isNotEmpty ? article.images.first : ''),
                        ),
                      ),
                    SizedBox(height: 24.h),
                  ],
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: 20.w),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 标题
                        Text(
                          article.title,
                          style: TextStyle(
                            fontSize: 26.sp,
                            fontWeight: FontWeight.w900,
                            color: contentText,
                            height: 1.3,
                          ),
                        ),
                        SizedBox(height: 20.h),
                        // 作者行
                        Row(
                          children: [
                            GestureDetector(
                              onTap: () => context.push('/user/$authorName'),
                              child: Row(
                                children: [
                                  CircleAvatar(
                                    radius: 21.r,
                                    backgroundImage: author.avatar.isNotEmpty
                                        ? NetworkImage(author.avatar)
                                        : null,
                                    backgroundColor: Colors.grey.shade300,
                                  ),
                                  SizedBox(width: 12.w),
                                  Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Text(
                                            authorName,
                                            style: TextStyle(
                                              fontSize: 15.sp,
                                              fontWeight: FontWeight.w700,
                                              color: contentText,
                                            ),
                                          ),
                                          if (author.badge != null) ...[
                                            SizedBox(width: 6.w),
                                            Container(
                                              padding: EdgeInsets.symmetric(horizontal: 6.w, vertical: 2.h),
                                              decoration: BoxDecoration(
                                                gradient: const LinearGradient(
                                                  colors: [Colors.orange, Colors.red],
                                                ),
                                                borderRadius: BorderRadius.circular(4.r),
                                              ),
                                              child: Text(
                                                author.badge!,
                                                style: TextStyle(fontSize: 9.sp, fontWeight: FontWeight.w700, color: Colors.white),
                                              ),
                                            ),
                                          ],
                                        ],
                                      ),
                                      SizedBox(height: 2.h),
                                      Text(
                                        '${article.date.isNotEmpty ? article.date : ''} · ${author.isOfficial ? context.l10n.officialAccount : context.l10n.seniorCreator}',
                                        style: TextStyle(fontSize: 12.sp, color: contentText.withValues(alpha: 0.6)),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            const Spacer(),
                            if (!_isFollowing)
                              TextButton(
                                onPressed: () => setState(() => _isFollowing = true),
                                style: TextButton.styleFrom(
                                  backgroundColor: AppColors.primaryColor,
                                  foregroundColor: Colors.white,
                                  padding: EdgeInsets.symmetric(horizontal: 20.w, vertical: 10.h),
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(999)),
                                ),
                                child: Text(context.l10n.follow, style: TextStyle(fontSize: 14.sp, fontWeight: FontWeight.w700)),
                              )
                            else
                              Container(
                                padding: EdgeInsets.symmetric(horizontal: 12.w, vertical: 8.h),
                                decoration: BoxDecoration(
                                  color: contentText.withValues(alpha: 0.1),
                                  borderRadius: BorderRadius.circular(999),
                                ),
                                child: Text(context.l10n.following, style: TextStyle(fontSize: 12.sp, color: contentText.withValues(alpha: 0.7))),
                              ),
                          ],
                        ),
                        SizedBox(height: 24.h),
                        // 正文
                        Text(
                          article.description,
                          style: TextStyle(
                            fontSize: 17.sp,
                            height: 1.8,
                            color: contentText,
                          ),
                        ),
                        SizedBox(height: 12.h),
                        Text(
                          _stripHtml(article.contentHtml),
                          style: TextStyle(
                            fontSize: 17.sp,
                            height: 1.8,
                            color: contentText,
                          ),
                        ),
                        SizedBox(height: 32.h),
                        // 著作权
                        Row(
                          children: [
                            Text(context.l10n.copyrightNotice, style: TextStyle(fontSize: 13.sp, color: contentText.withValues(alpha: 0.5))),
                            Text(' · ', style: TextStyle(color: contentText.withValues(alpha: 0.5))),
                            Text(context.l10n.commercialReproductionNotice, style: TextStyle(fontSize: 13.sp, color: contentText.withValues(alpha: 0.5))),
                          ],
                        ),
                        SizedBox(height: 16.h),
                        // 标签
                        Wrap(
                          spacing: 8.w,
                          runSpacing: 8.h,
                          children: ['生活方式', '深度好文', '推荐'].map((tag) {
                            return Container(
                              padding: EdgeInsets.symmetric(horizontal: 12.w, vertical: 6.h),
                              decoration: BoxDecoration(
                                color: contentText.withValues(alpha: 0.08),
                                borderRadius: BorderRadius.circular(999),
                              ),
                              child: Text('#$tag', style: TextStyle(fontSize: 12.sp, color: contentText.withValues(alpha: 0.7))),
                            );
                          }).toList(),
                        ),
                        SizedBox(height: 24.h),
                        Divider(height: 1, color: contentText.withValues(alpha: 0.1)),
                        SizedBox(height: 24.h),
                        // 评论区标题
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              context.l10n.allCommentsCount(_commentsCount),
                              style: TextStyle(fontSize: 18.sp, fontWeight: FontWeight.w700, color: contentText),
                            ),
                            Row(
                              children: [
                                Text(context.l10n.sortByHot, style: TextStyle(fontSize: 14.sp, color: contentText)),
                                SizedBox(width: 16.w),
                                Text(context.l10n.sortByNew, style: TextStyle(fontSize: 14.sp, color: contentText.withValues(alpha: 0.6))),
                              ],
                            ),
                          ],
                        ),
                        SizedBox(height: 16.h),
                        // 模拟评论
                        ...List.generate(3, (i) {
                          return Padding(
                            padding: EdgeInsets.only(bottom: 16.h),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                CircleAvatar(
                                  radius: 18.r,
                                  backgroundColor: contentText.withValues(alpha: 0.15),
                                  child: Text('U${i + 1}', style: TextStyle(fontSize: 12.sp, color: contentText)),
                                ),
                                SizedBox(width: 12.w),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Text('用户${9527 + i}', style: TextStyle(fontSize: 13.sp, fontWeight: FontWeight.w700, color: contentText)),
                                          const Spacer(),
                                          Icon(Icons.favorite_border, size: 14.sp, color: contentText.withValues(alpha: 0.5)),
                                          SizedBox(width: 4.w),
                                          Text('${10 + i * 3}', style: TextStyle(fontSize: 12.sp, color: contentText.withValues(alpha: 0.5))),
                                        ],
                                      ),
                                      SizedBox(height: 4.h),
                                      Text(
                                        i.isEven ? '这篇文章写得太好了，非常有启发性！支持作者继续更新～' : '观点很独特，不过我觉得第二点还有待商榷。',
                                        style: TextStyle(fontSize: 15.sp, color: contentText.withValues(alpha: 0.9), height: 1.4),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          );
                        }),
                        SizedBox(height: 100.h),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          // 底栏：点赞、评论、收藏、分享
          Container(
            padding: EdgeInsets.symmetric(
              horizontal: context.safeGetContainerSpacing(SpacingSize.md),
              vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
            ),
            decoration: BoxDecoration(
              color: contentBg,
              border: Border(top: BorderSide(color: contentText.withValues(alpha: 0.1))),
            ),
            child: SafeArea(
              top: false,
              child: Row(
                children: [
                  _actionChip(context, _isLiked ? Icons.favorite : Icons.favorite_border, _likesCount, _isLiked, AppColors.error, () {
                    setState(() {
                      _isLiked = !_isLiked;
                      _likesCount += _isLiked ? 1 : -1;
                      if (_likesCount < 0) _likesCount = 0;
                    });
                    if (_isLiked) {
                      ref.read(behaviorRepositoryProvider).reportSingle(
                        contentId: widget.articleId,
                        action: 'like',
                      );
                    }
                  }),
                  SizedBox(width: AppSpacing.interGroupLg),
                  _actionChip(context, Icons.chat_bubble_outline, _commentsCount, false, null, () {}),
                  SizedBox(width: AppSpacing.interGroupLg),
                  _actionChip(context, _isSaved ? Icons.star : Icons.star_border, 0, _isSaved, AppColors.warning, () {
                    setState(() => _isSaved = !_isSaved);
                    if (_isSaved) {
                      ref.read(behaviorRepositoryProvider).reportSingle(
                        contentId: widget.articleId,
                        action: 'favorite',
                      );
                    }
                  }),
                  SizedBox(width: AppSpacing.interGroupSm),
                  _actionChipLabel(context, Icons.share, UITextConstants.share, () {}),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _coverImage(String url) {
    if (url.isEmpty) return const SizedBox.shrink();
    return Image.network(
      url,
      fit: BoxFit.cover,
      errorBuilder: (_, __, ___) => Container(color: Colors.grey.shade300, child: const Icon(Icons.broken_image, size: 48)),
    );
  }

  Widget _actionChip(BuildContext context, IconData icon, int count, bool isActive, Color? activeColor, VoidCallback onTap) {
    final isDark = ref.watch(isDarkProvider);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 24.sp,
            color: isActive ? (activeColor ?? AppColors.primaryColor) : fg,
          ),
          SizedBox(height: 2.h),
          Text(
            count > 0 ? _formatCount(count) : '',
            style: TextStyle(fontSize: 10.sp, color: fg),
          ),
        ],
      ),
    );
  }

  Widget _actionChipLabel(BuildContext context, IconData icon, String label, VoidCallback onTap) {
    final isDark = ref.watch(isDarkProvider);
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: AppSpacing.iconMedium, color: fg),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            label,
            style: TextStyle(fontSize: AppTypography.xs, color: fg),
          ),
        ],
      ),
    );
  }

  String _formatCount(int n) {
    if (n >= 10000) return '${(n / 10000).toStringAsFixed(1)}w';
    if (n >= 1000) return '${(n / 1000).toStringAsFixed(1)}k';
    return '$n';
  }

  String _stripHtml(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]*>'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }
}
