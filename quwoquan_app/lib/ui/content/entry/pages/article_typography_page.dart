import 'dart:collection';
import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Material, MaterialType;
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/entry/models/create_editor_models.dart';
import 'package:quwoquan_app/ui/content/entry/publish_draft_projection_bridge.dart';
import 'package:quwoquan_app/ui/content/entry/providers/create_editor_provider.dart';
import 'package:quwoquan_app/ui/content/entry/widgets/article_typography_thumbnail_raster.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

enum _TypographyTab { paper, font }

/// 长文排版页：书页预览 + 底部排版面板（纸张/字体），顶部工具栏含返回、页码、标题、下一步。
/// 导航标题优先 [postReadPreviewBundleFromCreateEditorState] 的只读投影标题（draftPreview 表面）。
class ArticleTypographyPage extends ConsumerStatefulWidget {
  const ArticleTypographyPage({super.key});

  @override
  ConsumerState<ArticleTypographyPage> createState() =>
      _ArticleTypographyPageState();
}

class _ArticleTypographyPageState extends ConsumerState<ArticleTypographyPage> {
  static const double _thumbWidth = AppSpacing.largeAvatarSize;
  static const int _maxPreviewPageCacheEntries = 5;

  double _thumbHeight(double pageAspectRatio) =>
      _thumbWidth / pageAspectRatio + AppSpacing.intraGroupXs + AppSpacing.md;

  _TypographyTab _tab = _TypographyTab.paper;
  final LinkedHashMap<int, List<ArticlePageData>> _previewPagesCache =
      LinkedHashMap<int, List<ArticlePageData>>();

  int _previewPagesCacheKey(
    CreateEditorState state,
    BoxConstraints constraints,
    ArticleCanvasMetrics metrics,
  ) {
    return Object.hash(
      state.articleDocument,
      state.articleTemplate,
      state.articleFontPreset,
      state.articlePaperTexture,
      constraints.maxWidth.floor(),
      constraints.maxHeight.floor(),
      metrics.aspectRatio,
      metrics.outerPadding,
      metrics.contentPadding,
      metrics.headerReservedHeight,
      metrics.footerReservedHeight,
    );
  }

  List<ArticlePageData> _resolvePreviewPages(
    BuildContext context,
    CreateEditorState state,
    BoxConstraints constraints,
    ArticleCanvasMetrics metrics,
  ) {
    final cacheKey = _previewPagesCacheKey(state, constraints, metrics);
    final cached = _previewPagesCache.remove(cacheKey);
    if (cached != null) {
      _previewPagesCache[cacheKey] = cached;
      return cached;
    }
    final resolved = resolvePaginatedArticlePages(
      context: context,
      constraints: constraints,
      document: state.articleDocument,
      template: state.articleTemplate,
      fontPreset: state.articleFontPreset,
      fallbackPages: state.articlePages,
      variant: ArticleCanvasVariant.preview,
      paperTexture: state.articlePaperTexture,
    );
    _previewPagesCache[cacheKey] = resolved;
    while (_previewPagesCache.length > _maxPreviewPageCacheEntries) {
      _previewPagesCache.remove(_previewPagesCache.keys.first);
    }
    return resolved;
  }

  @override
  void initState() {
    super.initState();
    // 沉浸式深色状态栏
    SystemChrome.setSystemUIOverlayStyle(
      const SystemUiOverlayStyle(
        statusBarBrightness: Brightness.dark,
        statusBarIconBrightness: Brightness.light,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(createEditorProvider);
    final enablePageCurl = ref.watch(
      contentFeatureFlagProvider('enable_article_page_curl'),
    );

    return CupertinoPageScaffold(
      backgroundColor: AppColors.worksBackground,
      child: Material(
        type: MaterialType.transparency,
        child: Column(
          children: <Widget>[
            _buildTopBar(state),
            Expanded(
              child: LayoutBuilder(
                builder: (context, constraints) {
                  final metrics = resolveArticleCanvasMetrics(
                    context,
                    constraints,
                    variant: ArticleCanvasVariant.preview,
                  );
                  final pages = _resolvePreviewPages(
                    context,
                    state,
                    constraints,
                    metrics,
                  );
                  final idx = pages.indexWhere(
                    (p) => p.id == state.activeArticlePageId,
                  );
                  return Column(
                    children: <Widget>[
                      Expanded(
                        child: ColoredBox(
                          color: AppColors.worksBackground,
                          child: ArticleReadOnlyBookDeck(
                            pages: pages,
                            template: state.articleTemplate,
                            fontPreset: state.articleFontPreset,
                            metrics: metrics,
                            coverUrl: state.articleCoverImagePath,
                            paperTexture: state.articlePaperTexture,
                            initialPage: idx < 0 ? 0 : idx,
                            enablePageCurl: enablePageCurl,
                            pagePadding: EdgeInsets.zero,
                            showFooterPageLabel: false,
                            onPageChanged: (int i) {
                              if (i >= 0 && i < pages.length) {
                                ref
                                    .read(createEditorProvider.notifier)
                                    .setActiveArticlePage(pages[i].id);
                              }
                            },
                            onFallbackResolved: (reason) {
                              debugPrint(
                                'ArticleTypographyPage fallback: ${reason.name}',
                              );
                            },
                          ),
                        ),
                      ),
                      _buildTypographyPanel(state, constraints, metrics),
                    ],
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTopBar(CreateEditorState state) {
    final fg = AppColors.white;
    final fgSecondary = AppColors.white.withValues(alpha: 0.6);
    final draftRead = postReadPreviewBundleFromCreateEditorState(state);
    final barTitle = draftRead.presentation.title.trim().isNotEmpty
        ? draftRead.presentation.title
        : '长文排版';
    final pages = state.articlePages;
    final activeIdx = pages.indexWhere(
      (p) => p.id == state.activeArticlePageId,
    );
    final pageLabel = pages.length > 1 && activeIdx >= 0
        ? '${activeIdx + 1}/${pages.length}'
        : null;

    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: AppSpacing.sm, sigmaY: AppSpacing.sm),
        child: Container(
          padding: EdgeInsets.only(
            top: MediaQuery.viewPaddingOf(context).top,
            left: AppSpacing.containerSm,
            right: AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: AppColors.black,
            border: Border(
              bottom: BorderSide(
                color: AppColors.white.withValues(alpha: 0.12),
                width: AppSpacing.hairline,
              ),
            ),
          ),
          child: SizedBox(
            height: AppSpacing.toolbarHeight,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: <Widget>[
                // 返回按钮
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size.square(
                    AppSpacing.iconButtonMinSizeSm,
                  ),
                  onPressed: () => Navigator.of(context).pop(),
                  child: Icon(CupertinoIcons.back, color: fg),
                ),
                // 页码（紧跟返回按钮）
                if (pageLabel != null)
                  Padding(
                    padding: const EdgeInsets.only(left: 2),
                    child: Text(
                      pageLabel,
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        fontWeight: AppTypography.medium,
                        color: fgSecondary,
                      ),
                    ),
                  ),
                // 中间标题
                Expanded(
                  child: Center(
                    child: Text(
                      barTitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: fg,
                        fontSize: AppTypography.iosNavTitle,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ),
                ),
                // 下一步按钮
                CupertinoButton(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                  ),
                  minimumSize: const Size.square(AppSpacing.buttonHeightSm),
                  color: AppColors.iosAccentLight,
                  borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
                  onPressed: () => Navigator.of(context).pop(true),
                  child: const Text(
                    '下一步',
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTypographyPanel(
    CreateEditorState state,
    BoxConstraints layoutConstraints,
    ArticleCanvasMetrics metrics,
  ) {
    const panelBg = AppColors.black;
    final fg = AppColorsFunctional.getColor(true, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(
      true,
      ColorType.foregroundSecondary,
    );
    final separatorOpaque = AppColorsFunctional.getColor(
      true,
      ColorType.separatorOpaque,
    );
    final bottomPad = MediaQuery.of(context).padding.bottom;
    final pageAspect = metrics.aspectRatio;
    final panelListHeight = _thumbHeight(pageAspect);

    return Container(
      decoration: BoxDecoration(
        color: panelBg,
        border: Border(
          top: BorderSide(color: separatorOpaque, width: AppSpacing.hairline),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerMd,
                vertical: AppSpacing.intraGroupSm,
              ),
              child: Row(
                children: <Widget>[
                  // x 圆圈（关闭排版面板，返回编辑页）
                  GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () => Navigator.of(context).pop(),
                    child: SizedBox(
                      width: AppSpacing.minInteractiveSize,
                      height: AppSpacing.minInteractiveSize,
                      child: Center(
                        child: Icon(
                          CupertinoIcons.xmark_circle_fill,
                          size: AppSpacing.iconMedium,
                          color: fgSecondary,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.containerLg),
                  _buildTabItem(
                    label: '纸张',
                    selected: _tab == _TypographyTab.paper,
                    labelColor: fg,
                    secondaryColor: fgSecondary,
                    onTap: () => setState(() => _tab = _TypographyTab.paper),
                  ),
                  SizedBox(width: AppSpacing.containerLg),
                  _buildTabItem(
                    label: '字体',
                    selected: _tab == _TypographyTab.font,
                    labelColor: fg,
                    secondaryColor: fgSecondary,
                    onTap: () => setState(() => _tab = _TypographyTab.font),
                  ),
                  const Spacer(),
                ],
              ),
            ),
            SizedBox(
              height: panelListHeight,
              child: ArticleTypographyThumbnailStrip(
                editorState: state,
                layoutConstraints: layoutConstraints,
                metrics: metrics,
                coverUrl: state.articleCoverImagePath,
                activeTab: _tab == _TypographyTab.paper
                    ? ArticleTypographyThumbnailTab.paper
                    : ArticleTypographyThumbnailTab.font,
                child: _tab == _TypographyTab.paper
                    ? _buildPaperList(state, pageAspect, fg, fgSecondary)
                    : _buildFontList(state, pageAspect, fg, fgSecondary),
              ),
            ),
            SizedBox(height: bottomPad > 0 ? 0 : AppSpacing.intraGroupSm),
          ],
        ),
      ),
    );
  }

  Widget _buildTabItem({
    required String label,
    required bool selected,
    required Color labelColor,
    required Color secondaryColor,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: SizedBox(
        height: AppSpacing.minInteractiveSize,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Text(
              label,
              style: TextStyle(
                fontSize: AppTypography.base,
                fontWeight: selected
                    ? AppTypography.semiBold
                    : AppTypography.regular,
                color: selected ? labelColor : secondaryColor,
              ),
            ),
            SizedBox(height: AppSpacing.three),
            AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: selected ? AppSpacing.twenty : 0,
              height: AppSpacing.two,
              decoration: BoxDecoration(
                color: selected ? labelColor : labelColor.withValues(alpha: 0),
                borderRadius: BorderRadius.circular(AppSpacing.one),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPaperList(
    CreateEditorState state,
    double pageAspectRatio,
    Color fg,
    Color fgSecondary,
  ) {
    final thumbH = _thumbWidth / pageAspectRatio;
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      itemCount: ArticlePaperTexture.values.length,
      separatorBuilder: (_, _) => SizedBox(width: AppSpacing.containerSm),
      itemBuilder: (context, index) {
        final texture = ArticlePaperTexture.values[index];
        final isSelected = texture == state.articlePaperTexture;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            ref
                .read(createEditorProvider.notifier)
                .setArticlePaperTexture(texture);
          },
          child: SizedBox(
            width: _thumbWidth,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                ArticleTypographyRasterCell(
                  paper: texture,
                  font: state.articleFontPreset,
                  width: _thumbWidth,
                  height: thumbH,
                  isSelected: isSelected,
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  texture.label,
                  style: TextStyle(
                    fontSize: AppTypography.xxs,
                    fontWeight: isSelected
                        ? AppTypography.semiBold
                        : AppTypography.regular,
                    color: isSelected ? fg : fgSecondary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildFontList(
    CreateEditorState state,
    double pageAspectRatio,
    Color fg,
    Color fgSecondary,
  ) {
    final thumbH = _thumbWidth / pageAspectRatio;
    return ListView.separated(
      scrollDirection: Axis.horizontal,
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      itemCount: ArticleFontPreset.values.length,
      separatorBuilder: (_, _) => SizedBox(width: AppSpacing.containerSm),
      itemBuilder: (context, index) {
        final preset = ArticleFontPreset.values[index];
        final isSelected = preset == state.articleFontPreset;
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () {
            ref
                .read(createEditorProvider.notifier)
                .setArticleFontPreset(preset);
          },
          child: SizedBox(
            width: _thumbWidth,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                ArticleTypographyRasterCell(
                  paper: state.articlePaperTexture,
                  font: preset,
                  width: _thumbWidth,
                  height: thumbH,
                  isSelected: isSelected,
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  preset.label,
                  style: TextStyle(
                    fontSize: AppTypography.xxs,
                    fontWeight: isSelected
                        ? AppTypography.semiBold
                        : AppTypography.regular,
                    color: isSelected ? fg : fgSecondary,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
