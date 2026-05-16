import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

import 'qwq_markdown_ast.dart';
import 'qwq_markdown_pagination.dart';

class ImmersiveMarkdownReader extends StatelessWidget {
  const ImmersiveMarkdownReader({
    super.key,
    required this.document,
    this.engine = const MarkdownPaginationEngine(),
  });

  final QwqMarkdownDocument document;
  final MarkdownPaginationEngine engine;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final mediaQuery = MediaQuery.maybeOf(context);
        final size = Size(
          constraints.maxWidth.isFinite ? constraints.maxWidth : 390,
          constraints.maxHeight.isFinite ? constraints.maxHeight : 720,
        );
        final pages = engine.paginate(
          document: document,
          profile: QwqMarkdownPaginationProfile(
            viewportSize: size,
            textScaleFactor: mediaQuery?.textScaleFactor ?? 1,
            template: document.frontMatter.template.isEmpty
                ? 'journal'
                : document.frontMatter.template,
            fontPreset: document.frontMatter.fontPreset.isEmpty
                ? 'clean'
                : document.frontMatter.fontPreset,
          ),
        );
        return PageView.builder(
          itemCount: pages.length,
          itemBuilder: (context, index) {
            return QwqMarkdownPageSurface(page: pages[index]);
          },
        );
      },
    );
  }
}

class QwqMarkdownPageSurface extends StatelessWidget {
  const QwqMarkdownPageSurface({super.key, required this.page});

  final QwqMarkdownPageData page;

  @override
  Widget build(BuildContext context) {
    final theme = CupertinoTheme.of(context);
    return DecoratedBox(
      decoration: const BoxDecoration(color: CupertinoColors.systemBackground),
      child: SafeArea(
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: page.profile.horizontalPadding,
            vertical: page.profile.verticalPadding,
          ),
          child: ListView(
            physics: const NeverScrollableScrollPhysics(),
            children: [
              for (final block in page.blocks) _MarkdownBlockView(block: block),
              Text(
                '${page.pageIndex + 1}',
                textAlign: TextAlign.center,
                style: theme.textTheme.textStyle.copyWith(
                  color: CupertinoColors.secondaryLabel.resolveFrom(context),
                  fontSize: AppTypography.sm,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MarkdownBlockView extends StatelessWidget {
  const _MarkdownBlockView({required this.block});

  final QwqMarkdownBlock block;

  @override
  Widget build(BuildContext context) {
    final theme = CupertinoTheme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.fourteen),
      child: switch (block.kind) {
        QwqMarkdownBlockKind.heading => Text(
          block.text,
          style: theme.textTheme.navLargeTitleTextStyle.copyWith(
            fontSize: block.level <= 1 ? 30 : 24,
          ),
        ),
        QwqMarkdownBlockKind.figure ||
        QwqMarkdownBlockKind.image => _AssetPlaceholder(asset: block.assetRef),
        QwqMarkdownBlockKind.gallery => _GalleryPlaceholder(
          assets: block.assetRefs,
        ),
        QwqMarkdownBlockKind.callout => _CalloutBlock(block: block),
        QwqMarkdownBlockKind.card => _CardBlock(block: block),
        QwqMarkdownBlockKind.horizontalRule => const SizedBox(height: AppSpacing.lg),
        QwqMarkdownBlockKind.spacer => const SizedBox(height: AppSpacing.lg),
        QwqMarkdownBlockKind.codeBlock => Text(
          block.text,
          style: theme.textTheme.textStyle.copyWith(
            fontFamily: 'monospace',
            fontSize: AppTypography.smPlus,
          ),
        ),
        _ => Text(
          block.text,
          style: theme.textTheme.textStyle.copyWith(
            fontSize: AppTypography.iosBody,
            height: AppSpacing.textLineHeightLabel,
          ),
        ),
      },
    );
  }
}

class _AssetPlaceholder extends StatelessWidget {
  const _AssetPlaceholder({required this.asset});

  final QwqMarkdownAssetRef? asset;

  @override
  Widget build(BuildContext context) {
    final id = asset?.assetId ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          height: AppSpacing.oneHundred + AppSpacing.forty + AppSpacing.forty,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: CupertinoColors.systemGrey5.resolveFrom(context),
            borderRadius: BorderRadius.circular(AppSpacing.radiusEighteen),
          ),
          child: Text(id.isEmpty ? 'asset' : id),
        ),
        if ((asset?.caption ?? '').isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: AppSpacing.six),
            child: Text(
              asset!.caption,
              textAlign: TextAlign.center,
              style: CupertinoTheme.of(context).textTheme.textStyle.copyWith(
                color: CupertinoColors.secondaryLabel.resolveFrom(context),
                fontSize: AppTypography.smPlus,
              ),
            ),
          ),
      ],
    );
  }
}

class _GalleryPlaceholder extends StatelessWidget {
  const _GalleryPlaceholder({required this.assets});

  final List<QwqMarkdownAssetRef> assets;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        for (final asset in assets)
          Container(
            width: AppSpacing.welcomePetalHeight,
            height: AppSpacing.welcomePetalHeight,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: CupertinoColors.systemGrey5.resolveFrom(context),
              borderRadius: BorderRadius.circular(AppSpacing.fourteen),
            ),
            child: Text(asset.assetId),
          ),
      ],
    );
  }
}

class _CalloutBlock extends StatelessWidget {
  const _CalloutBlock({required this.block});

  final QwqMarkdownBlock block;

  @override
  Widget build(BuildContext context) {
    final title = block.attributes['title']?.toString() ?? '提示';
    return Container(
      padding: const EdgeInsets.all(AppSpacing.fourteen),
      decoration: BoxDecoration(
        color: CupertinoColors.systemYellow.withOpacity(0.16),
        borderRadius: BorderRadius.circular(AppSpacing.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: CupertinoTheme.of(
              context,
            ).textTheme.textStyle.copyWith(fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: AppSpacing.six),
          Text(block.text),
        ],
      ),
    );
  }
}

class _CardBlock extends StatelessWidget {
  const _CardBlock({required this.block});

  final QwqMarkdownBlock block;

  @override
  Widget build(BuildContext context) {
    final title = block.attributes['title']?.toString() ?? '卡片';
    return Container(
      padding: const EdgeInsets.all(AppSpacing.fourteen),
      decoration: BoxDecoration(
        border: Border.all(
          color: CupertinoColors.separator.resolveFrom(context),
        ),
        borderRadius: BorderRadius.circular(AppSpacing.md),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: CupertinoTheme.of(
              context,
            ).textTheme.textStyle.copyWith(fontWeight: FontWeight.w600),
          ),
          if (block.text.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.six),
            Text(block.text),
          ],
        ],
      ),
    );
  }
}
