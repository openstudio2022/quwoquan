import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class ArticlePreviewPage extends ConsumerStatefulWidget {
  const ArticlePreviewPage({super.key});

  @override
  ConsumerState<ArticlePreviewPage> createState() => _ArticlePreviewPageState();
}

class _ArticlePreviewPageState extends ConsumerState<ArticlePreviewPage> {
  late final PageController _pageController;

  @override
  void initState() {
    super.initState();
    _pageController = PageController();
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(createEditorProvider);
    final pages = state.articlePages;

    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground.resolveFrom(context),
      child: SafeArea(
        bottom: false,
        child: Column(
          children: <Widget>[
            _PreviewHeader(
              onBack: () => Navigator.of(context).pop(false),
              onNext: () => Navigator.of(context).pop(true),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pageController,
                itemCount: pages.length,
                onPageChanged: (_) => setState(() {}),
                itemBuilder: (context, index) {
                  final page = pages[index];
                  return Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.containerSm,
                    ),
                    child: ArticlePageShell(
                      template: state.articleTemplate,
                      fontPreset: state.articleFontPreset,
                      pageIndex: index,
                      totalPages: pages.length,
                      child: ArticlePageReadOnlyView(
                        page: page,
                        template: state.articleTemplate,
                        fontPreset: state.articleFontPreset,
                      ),
                    ),
                  );
                },
              ),
            ),
            Container(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerMd,
                AppSpacing.containerSm,
                AppSpacing.containerMd,
                MediaQuery.viewPaddingOf(context).bottom + AppSpacing.containerMd,
              ),
              decoration: BoxDecoration(
                color: CupertinoColors.systemBackground.resolveFrom(context),
                border: Border(
                  top: BorderSide(
                    color: CupertinoColors.separator
                        .resolveFrom(context)
                        .withValues(alpha: 0.15),
                  ),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: ArticleTemplatePreset.values.map((template) {
                        return Padding(
                          padding: EdgeInsets.only(right: AppSpacing.containerSm),
                          child: ArticleTemplateThumbnail(
                            template: template,
                            fontPreset: state.articleFontPreset,
                            label: template.label,
                            selected: state.articleTemplate == template,
                            onTap: () => ref
                                .read(createEditorProvider.notifier)
                                .setArticleTemplate(template),
                          ),
                        );
                      }).toList(growable: false),
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  Text(
                    '选一个喜欢的卡片',
                    style: TextStyle(
                      color: CupertinoColors.secondaryLabel.resolveFrom(context),
                      fontSize: AppTypography.base,
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  SizedBox(
                    height: AppSpacing.buttonHeight + AppSpacing.intraGroupXs,
                    child: CupertinoButton(
                      color: AppColors.iosAccentLight,
                      borderRadius: BorderRadius.circular(AppSpacing.radiusTwentyEight),
                      onPressed: () => Navigator.of(context).pop(true),
                      child: const Text(
                        '下一步',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: AppTypography.xl,
                          fontWeight: AppTypography.medium,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PreviewHeader extends StatelessWidget {
  const _PreviewHeader({
    required this.onBack,
    required this.onNext,
  });

  final VoidCallback onBack;
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: AppSpacing.toolbarHeight,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Stack(
        alignment: Alignment.center,
        children: <Widget>[
          Align(
            alignment: Alignment.centerLeft,
            child: CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
              onPressed: onBack,
              child: Icon(
                CupertinoIcons.back,
                color: CupertinoColors.label.resolveFrom(context),
              ),
            ),
          ),
          Text(
            '预览',
            style: TextStyle(
              color: CupertinoColors.label.resolveFrom(context),
              fontSize: AppTypography.xl,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          Align(
            alignment: Alignment.centerRight,
            child: CupertinoButton(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
              minimumSize: const Size.square(AppSpacing.iconButtonMinSizeSm),
              color: AppColors.iosAccentLight,
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              onPressed: onNext,
              child: const Text(
                '下一步',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: AppTypography.base,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
