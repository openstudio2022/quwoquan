import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

class ArticlePreviewPage extends ConsumerWidget {
  const ArticlePreviewPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(createEditorProvider);
    final enablePageCurl = ref.watch(
      contentFeatureFlagProvider('enable_article_page_curl'),
    );
    final coverCandidates = <String>[
      if (state.articleCoverImagePath.trim().isNotEmpty &&
          !state.imagePaths.contains(state.articleCoverImagePath.trim()))
        state.articleCoverImagePath.trim(),
      ...state.imagePaths.where((path) => path.trim().isNotEmpty),
    ];

    return CupertinoPageScaffold(
      backgroundColor: CupertinoColors.systemGroupedBackground.resolveFrom(
        context,
      ),
      child: SafeArea(
        bottom: false,
        child: Column(
          children: <Widget>[
            _PreviewHeader(
              onBack: () => Navigator.of(context).pop(false),
              onNext: () => Navigator.of(context).pop(true),
            ),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final pages = resolvePaginatedArticlePages(
                    context: context,
                    constraints: constraints,
                    document: state.articleDocument,
                    template: state.articleTemplate,
                    fontPreset: state.articleFontPreset,
                    fallbackPages: state.articlePages,
                    variant: ArticleCanvasVariant.preview,
                  );
                  final metrics = resolveArticleCanvasMetrics(
                    context,
                    constraints,
                    variant: ArticleCanvasVariant.preview,
                  );
                  return ArticleReadOnlyBookDeck(
                    pages: pages,
                    template: state.articleTemplate,
                    fontPreset: state.articleFontPreset,
                    metrics: metrics,
                    coverUrl: state.articleCoverImagePath,
                    enablePageCurl: enablePageCurl,
                    pagePadding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                      vertical: AppSpacing.containerSm,
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
                MediaQuery.viewPaddingOf(context).bottom +
                    AppSpacing.containerMd,
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
                  if (coverCandidates.isNotEmpty ||
                      state.articleCoverImagePath
                          .trim()
                          .isNotEmpty) ...<Widget>[
                    Text(
                      '扉页封面',
                      style: TextStyle(
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
                        fontSize: AppTypography.xsPlus,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupSm),
                    SingleChildScrollView(
                      key: TestKeys.articlePreviewCoverStrip,
                      scrollDirection: Axis.horizontal,
                      child: Row(
                        children: <Widget>[
                          _PreviewCoverOption(
                            key: TestKeys.createArticleCoverNoneOption,
                            label: '无封面',
                            selected: state.articleCoverImagePath
                                .trim()
                                .isEmpty,
                            onTap: () => ref
                                .read(createEditorProvider.notifier)
                                .setArticleCoverImage(null),
                          ),
                          for (
                            var index = 0;
                            index < coverCandidates.length;
                            index += 1
                          )
                            Padding(
                              padding: EdgeInsets.only(
                                left: AppSpacing.containerSm,
                              ),
                              child: _PreviewCoverOption(
                                key: ValueKey<String>(
                                  'article_preview_cover_option_$index',
                                ),
                                label: '封面 ${index + 1}',
                                imagePath: coverCandidates[index],
                                selected:
                                    state.articleCoverImagePath ==
                                    coverCandidates[index],
                                onTap: () => ref
                                    .read(createEditorProvider.notifier)
                                    .setArticleCoverImage(
                                      coverCandidates[index],
                                    ),
                              ),
                            ),
                        ],
                      ),
                    ),
                    SizedBox(height: AppSpacing.interGroupSm),
                  ],
                  Text(
                    '模版',
                    style: TextStyle(
                      color: CupertinoColors.secondaryLabel.resolveFrom(
                        context,
                      ),
                      fontSize: AppTypography.xsPlus,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: ArticleTemplatePreset.values
                          .map((template) {
                            return Padding(
                              padding: EdgeInsets.only(
                                right: AppSpacing.containerSm,
                              ),
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
                          })
                          .toList(growable: false),
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  Text(
                    '字体',
                    style: TextStyle(
                      color: CupertinoColors.secondaryLabel.resolveFrom(
                        context,
                      ),
                      fontSize: AppTypography.xsPlus,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: ArticleFontPreset.values
                          .map((preset) {
                            final selected = state.articleFontPreset == preset;
                            return Padding(
                              padding: EdgeInsets.only(
                                right: AppSpacing.containerSm,
                              ),
                              child: CupertinoButton(
                                padding: EdgeInsets.symmetric(
                                  horizontal: AppSpacing.containerSm,
                                  vertical: AppSpacing.intraGroupXs,
                                ),
                                minimumSize: Size.zero,
                                color: selected
                                    ? AppColors.iosAccentLight
                                    : CupertinoColors.secondarySystemBackground
                                          .resolveFrom(context),
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.radiusTwenty,
                                ),
                                onPressed: () => ref
                                    .read(createEditorProvider.notifier)
                                    .setArticleFontPreset(preset),
                                child: Text(
                                  preset.label,
                                  style: TextStyle(
                                    color: selected
                                        ? AppColors.white
                                        : CupertinoColors.label.resolveFrom(
                                            context,
                                          ),
                                    fontSize: AppTypography.sm,
                                    fontWeight: AppTypography.medium,
                                  ),
                                ),
                              ),
                            );
                          })
                          .toList(growable: false),
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  Text(
                    '模板、封面与翻页壳层会直接同步到阅读页',
                    style: TextStyle(
                      color: CupertinoColors.secondaryLabel.resolveFrom(
                        context,
                      ),
                      fontSize: AppTypography.base,
                    ),
                  ),
                  SizedBox(height: AppSpacing.interGroupSm),
                  SizedBox(
                    height: AppSpacing.buttonHeight + AppSpacing.intraGroupXs,
                    child: CupertinoButton(
                      color: AppColors.iosAccentLight,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.radiusTwentyEight,
                      ),
                      onPressed: () => Navigator.of(context).pop(true),
                      child: const Text(
                        '下一步',
                        style: TextStyle(
                          color: AppColors.white,
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
  const _PreviewHeader({required this.onBack, required this.onNext});

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
                  color: AppColors.white,
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

class _PreviewCoverOption extends StatelessWidget {
  const _PreviewCoverOption({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.imagePath,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final String? imagePath;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        width:
            AppSpacing.avatarUserXl +
            AppSpacing.containerSm +
            AppSpacing.intraGroupXs,
        padding: EdgeInsets.all(AppSpacing.intraGroupXs),
        decoration: BoxDecoration(
          color: selected
              ? AppColors.iosAccentLight.withValues(alpha: 0.1)
              : CupertinoColors.secondarySystemBackground.resolveFrom(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(
            color: selected
                ? AppColors.iosAccentLight
                : CupertinoColors.separator
                      .resolveFrom(context)
                      .withValues(alpha: 0.2),
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
              child: SizedBox(
                height:
                    AppSpacing.avatarUserXl +
                    AppSpacing.containerSm +
                    AppSpacing.intraGroupXs,
                width: double.infinity,
                child: imagePath == null || imagePath!.trim().isEmpty
                    ? DecoratedBox(
                        decoration: BoxDecoration(
                          color: CupertinoColors.systemFill.resolveFrom(
                            context,
                          ),
                        ),
                        child: Center(
                          child: Icon(
                            CupertinoIcons.book,
                            color: CupertinoColors.secondaryLabel.resolveFrom(
                              context,
                            ),
                            size: AppSpacing.iconMedium,
                          ),
                        ),
                      )
                    : ArticleAdaptiveImage(imageUrl: imagePath!),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: CupertinoColors.label.resolveFrom(context),
                fontSize: AppTypography.xsPlus,
                fontWeight: selected
                    ? AppTypography.semiBold
                    : AppTypography.medium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
