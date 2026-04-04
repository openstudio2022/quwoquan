import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

/// 文章预览：横向翻页 + 书本透视（对标作品沉浸浏览的深色底与跟手分页）。
class ArticlePreviewBookPager extends StatefulWidget {
  const ArticlePreviewBookPager({
    super.key,
    required this.pages,
    required this.template,
    required this.fontPreset,
    required this.initialPageIndex,
    required this.onPageChanged,
  });

  final List<ArticlePageData> pages;
  final ArticleTemplatePreset template;
  final ArticleFontPreset fontPreset;
  final int initialPageIndex;
  final ValueChanged<int> onPageChanged;

  @override
  State<ArticlePreviewBookPager> createState() =>
      _ArticlePreviewBookPagerState();
}

class _ArticlePreviewBookPagerState extends State<ArticlePreviewBookPager> {
  late final PageController _controller;

  @override
  void initState() {
    super.initState();
    final maxI = math.max(0, widget.pages.length - 1);
    final i = widget.initialPageIndex.clamp(0, maxI);
    _controller = PageController(initialPage: i);
  }

  @override
  void didUpdateWidget(covariant ArticlePreviewBookPager oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.pages.length != widget.pages.length &&
        _controller.hasClients) {
      final page = _controller.page?.round() ?? 0;
      final maxI = math.max(0, widget.pages.length - 1);
      _controller.jumpToPage(page.clamp(0, maxI));
    }
    if (oldWidget.initialPageIndex != widget.initialPageIndex &&
        _controller.hasClients) {
      final maxI = math.max(0, widget.pages.length - 1);
      _controller.jumpToPage(widget.initialPageIndex.clamp(0, maxI));
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.pages.isEmpty) {
      return const SizedBox.shrink();
    }
    return ColoredBox(
      color: AppColors.worksBackground,
      child: PageView.builder(
        key: TestKeys.articlePreviewBookPager,
        controller: _controller,
        itemCount: widget.pages.length,
        onPageChanged: widget.onPageChanged,
        itemBuilder: (context, index) {
          final page = widget.pages[index];
          return _BookFlipPage(
            index: index,
            controller: _controller,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.containerSm,
              ),
              child: ArticlePageShell(
                template: widget.template,
                fontPreset: widget.fontPreset,
                pageIndex: index,
                totalPages: widget.pages.length,
                showIndicator: false,
                footerLabel: '${index + 1}/${widget.pages.length}',
                child: ArticlePageReadOnlyView(
                  page: page,
                  template: widget.template,
                  fontPreset: widget.fontPreset,
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _BookFlipPage extends StatelessWidget {
  const _BookFlipPage({
    required this.index,
    required this.controller,
    required this.child,
  });

  final int index;
  final PageController controller;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        var delta = 0.0;
        if (controller.hasClients && controller.position.haveDimensions) {
          final page = controller.page;
          if (page != null) {
            delta = page - index;
          }
        }
        final angle = delta.clamp(-1.0, 1.0) * 0.14;
        final opacity = 1.0 - (delta.abs() * 0.12).clamp(0.0, 0.22);
        return Opacity(
          opacity: opacity,
          child: Transform(
            alignment: Alignment.center,
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.001)
              ..rotateY(angle),
            child: child,
          ),
        );
      },
    );
  }
}
