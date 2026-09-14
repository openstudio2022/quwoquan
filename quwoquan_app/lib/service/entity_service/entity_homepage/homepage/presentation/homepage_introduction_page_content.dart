part of 'homepage_introduction_page.dart';

/// introduction 资产是否声明为 signedGrant 私有交付（DEC-033）。
/// assetId 缺席仍进入 typed 入口并 fail-closed，不预过滤成缺席。
bool _declaresSignedGrantIntroAsset(HomepageIntroductionAsset asset) {
  return asset.accessMode == MediaDeliveryAccessMode.signedGrant;
}

class _IntroductionHero extends StatelessWidget {
  const _IntroductionHero({required this.introduction});

  final HomepageIntroduction introduction;

  /// hero cover 是否声明为 signedGrant 私有交付（DEC-033）。assetId 缺席仍
  /// 进入 typed 入口并呈现不可恢复的投影矛盾终态。
  bool get _declaresSignedGrantCover =>
      introduction.coverAccessMode == MediaDeliveryAccessMode.signedGrant;

  @override
  Widget build(BuildContext context) {
    final coverUrl = (introduction.coverUrl ?? '').trim();
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
      child: Container(
        height: _introHeroHeight,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: <Color>[
              AppColors.primaryColor.withValues(alpha: 0.28),
              AppColors.primaryColor.withValues(alpha: 0.08),
            ],
          ),
        ),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            // DEC-033：hero cover 经统一 typed 分流入口，不再直接 import
            // original_access_quota 对象的私有表现件。
            if (_declaresSignedGrantCover || coverUrl.isNotEmpty)
              mediaDeliveryImage(
                binding: MediaDeliveryBinding(
                  assetId: introduction.coverAssetId?.trim() ?? '',
                  accessMode: introduction.coverAccessMode,
                  publicUrl: coverUrl,
                ),
                kind: MediaDeliveryKind.image,
                fit: BoxFit.cover,
                placeholder: const SizedBox.shrink(),
                absentWidget: const SizedBox.shrink(),
                publicBuilder: (context, publicUrl) => AppMediaImage(
                  imageSource: publicUrl,
                  fit: BoxFit.cover,
                  placeholder: const SizedBox.shrink(),
                  errorWidget: const SizedBox.shrink(),
                ),
              ),
            // 纯视觉暗纱不得拦截底下媒体失败态的重试手势。
            IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: <Color>[
                      AppColors.black.withValues(alpha: 0.04),
                      AppColors.black.withValues(alpha: 0.50),
                    ],
                  ),
                ),
              ),
            ),
            Positioned(
              left: AppSpacing.containerMd,
              right: AppSpacing.containerMd,
              bottom: AppSpacing.containerMd,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    UITextConstants.objectIntroTitle(introduction.displayName),
                    style: const TextStyle(
                      color: CupertinoColors.white,
                      fontSize: AppTypography.iosTitle2,
                      fontWeight: AppTypography.bold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    homepageTypeLabel(introduction.homepageType),
                    style: TextStyle(
                      color: CupertinoColors.white.withValues(alpha: 0.84),
                      fontSize: AppTypography.iosSubheadline,
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

class _IntroductionSectionCard extends StatelessWidget {
  const _IntroductionSectionCard({required this.section});

  final HomepageIntroductionSection section;

  /// 三段结构正文章节（kind=body/overview）：assets 是正文 figure 的
  /// role=inline 绑定，只用于块级内嵌渲染，不再重复展示横滑图条。
  bool get _assetsInlineOnly =>
      section.kind == 'body' || section.kind == 'overview';

  @override
  Widget build(BuildContext context) {
    final assetsById = <String, HomepageIntroductionAsset>{
      for (final asset in section.assets)
        if (asset.assetId.isNotEmpty) asset.assetId: asset,
    };
    // inline-only section 无横滑兜底；signedGrant 若连 assetId 都缺失，无法被
    // markdown 的 asset://<id> 引用命中，但仍必须显式 fail-closed，不能静默消失。
    // public/契约缺席且无可渲染来源继续保持 absent，不额外占用正文空间。
    final contradictoryInlineAssets = _assetsInlineOnly
        ? section.assets
              .where(
                (asset) =>
                    _declaresSignedGrantIntroAsset(asset) &&
                    asset.assetId.trim().isEmpty,
              )
              .toList(growable: false)
        : const <HomepageIntroductionAsset>[];
    return _IntroductionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            section.title,
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          if (section.semanticDocument != null ||
              (section.bodyMarkdown ?? '').trim().isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            HomepageMarkdownContent(
              semanticDocument: section.semanticDocument,
              markdown: section.semanticDocument == null
                  ? section.bodyMarkdown?.trim()
                  : null,
              assetsById: assetsById,
            ),
          ],
          for (final asset in contradictoryInlineAssets) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            _InlineFigure(asset: asset, caption: (asset.caption ?? '').trim()),
          ],
          if (section.timelineItems.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.containerSm),
            _TimelineList(items: section.timelineItems),
          ],
          if (section.assets.isNotEmpty && !_assetsInlineOnly) ...<Widget>[
            SizedBox(height: AppSpacing.containerSm),
            _AssetStrip(assets: section.assets),
          ],
        ],
      ),
    );
  }
}

/// Homepage canonical/legacy 正文的单一适配入口。canonical payload 在场时
/// 必须完整验证；任何失败均 typed unavailable，绝不回退 bodyMarkdown。
class HomepageMarkdownDocumentAdapter {
  HomepageMarkdownDocumentAdapter._({required this.document, this.errorCode});

  factory HomepageMarkdownDocumentAdapter.canonical(
    homepage_semantic.DocumentEnvelope envelope,
  ) {
    final wire = homepage_semantic.documentEnvelopeToWire(envelope);
    final result = homepage_semantic.validateSemanticDocumentEnvelope(
      wire,
      const <homepage_semantic.CapabilityId>{
        'parse.markdown',
        'parse.html',
        'serialize.markdown',
        'serialize.semantic_json',
        'render.app',
        'render.web',
        'render.workbench',
        'author.create',
        'author.editContent',
        'author.editStructure',
        'author.delete',
      },
    );
    if (result.code != homepage_semantic.SemanticDocumentValidationCode.ok) {
      return HomepageMarkdownDocumentAdapter._(
        document: null,
        errorCode: result.code.name,
      );
    }
    final digest = envelope.canonicalDigest;
    final fingerprint = envelope.semanticFingerprint;
    if (!_canonicalSha256.hasMatch(digest) ||
        !_canonicalSha256.hasMatch(fingerprint)) {
      return HomepageMarkdownDocumentAdapter._(
        document: null,
        errorCode: 'semantic_identity_invalid',
      );
    }
    final digestFields = Map<String, Object?>.from(wire)
      ..remove('canonicalDigest');
    final actual =
        'sha256:${sha256.convert(utf8.encode(jsonEncode(digestFields)))}';
    if (actual != digest || !_validateNodeFingerprints(envelope.nodes)) {
      return HomepageMarkdownDocumentAdapter._(
        document: null,
        errorCode: 'semantic_identity_drift',
      );
    }
    return HomepageMarkdownDocumentAdapter._(
      document: QwqMarkdownDocument(
        source: '',
        blocks: envelope.nodes.map(_canonicalBlock).toList(growable: false),
      ),
    );
  }

  factory HomepageMarkdownDocumentAdapter.parse(String markdown) {
    final result = const QwqMarkdownParser().parse(
      markdown,
      requireVersion: true,
    );
    return HomepageMarkdownDocumentAdapter._(
      document: result.document.hasBlockingDiagnostics ? null : result.document,
      errorCode: result.document.hasBlockingDiagnostics
          ? 'semantic_markdown_unavailable'
          : null,
    );
  }

  factory HomepageMarkdownDocumentAdapter.legacy(String markdown) {
    final result = const QwqMarkdownParser().parse(
      markdown,
      requireVersion: true,
    );
    return HomepageMarkdownDocumentAdapter._(
      document: result.document.hasBlockingDiagnostics ? null : result.document,
      errorCode: result.document.hasBlockingDiagnostics
          ? 'legacy_semantic_unavailable'
          : null,
    );
  }

  final QwqMarkdownDocument? document;
  final String? errorCode;
  bool get isAvailable => document != null;
  List<String> get semanticKinds {
    final envelope = document?.semanticEnvelope;
    if (envelope != null) {
      return envelope.nodes
          .map((node) => node.kind.name)
          .toList(growable: false);
    }
    return document?.blocks
            .map((block) => semanticNodeKindForQwqBlock(block.kind).name)
            .toList(growable: false) ??
        const <String>[];
  }

  List<String> get semanticTexts =>
      document?.blocks.map((block) => block.text).toList(growable: false) ??
      const <String>[];
  String? get semanticFingerprint =>
      document?.semanticEnvelope?.semanticFingerprint;
  List<String> get requiredCapabilities =>
      document?.semanticEnvelope?.requiredCapabilities ?? const <String>[];
}

final RegExp _canonicalSha256 = RegExp(r'^sha256:[0-9a-f]{64}$');

bool _validateNodeFingerprints(List<homepage_semantic.SemanticNode> nodes) {
  for (final node in nodes) {
    if (!_canonicalSha256.hasMatch(node.semanticFingerprint) ||
        !_validateNodeFingerprints(node.children)) {
      return false;
    }
    if (node.rawSlice != null) {
      final expected = 'sha256:${sha256.convert(utf8.encode(node.rawSlice!))}';
      if (node.rawSliceFingerprint != expected) return false;
    }
  }
  return true;
}

QwqMarkdownBlock _canonicalBlock(homepage_semantic.SemanticNode node) {
  final text = node.attributes['text']?.toString() ?? '';
  final kind = switch (node.kind) {
    homepage_semantic.SemanticNodeKind.heading => QwqMarkdownBlockKind.heading,
    homepage_semantic.SemanticNodeKind.list ||
    homepage_semantic.SemanticNodeKind.listItem =>
      QwqMarkdownBlockKind.bulletItem,
    homepage_semantic.SemanticNodeKind.blockquote => QwqMarkdownBlockKind.quote,
    homepage_semantic.SemanticNodeKind.codeBlock ||
    homepage_semantic.SemanticNodeKind.preformatted =>
      QwqMarkdownBlockKind.codeBlock,
    homepage_semantic.SemanticNodeKind.figure => QwqMarkdownBlockKind.figure,
    homepage_semantic.SemanticNodeKind.gallery => QwqMarkdownBlockKind.gallery,
    homepage_semantic.SemanticNodeKind.callout => QwqMarkdownBlockKind.callout,
    homepage_semantic.SemanticNodeKind.table => QwqMarkdownBlockKind.table,
    homepage_semantic.SemanticNodeKind.groupedDirectory =>
      QwqMarkdownBlockKind.groupedDirectory,
    homepage_semantic.SemanticNodeKind.definitionList =>
      QwqMarkdownBlockKind.definitionList,
    homepage_semantic.SemanticNodeKind.footnoteDefinition ||
    homepage_semantic.SemanticNodeKind.footnoteList ||
    homepage_semantic.SemanticNodeKind.footnoteReference =>
      QwqMarkdownBlockKind.footnote,
    homepage_semantic.SemanticNodeKind.paragraph ||
    homepage_semantic.SemanticNodeKind.section =>
      QwqMarkdownBlockKind.paragraph,
    _ => QwqMarkdownBlockKind.unsupported,
  };
  return QwqMarkdownBlock(
    id: node.nodeId,
    kind: kind,
    text: text,
    level: node.attributes['level'] is int
        ? node.attributes['level']! as int
        : 0,
    rawSource: node.rawSlice ?? '',
  );
}

class HomepageMarkdownContent extends StatelessWidget {
  const HomepageMarkdownContent({
    super.key,
    this.semanticDocument,
    this.markdown,
    this.assetsById = const <String, HomepageIntroductionAsset>{},
  });

  final homepage_semantic.DocumentEnvelope? semanticDocument;
  final String? markdown;
  final Map<String, HomepageIntroductionAsset> assetsById;

  @override
  Widget build(BuildContext context) {
    final canonical = semanticDocument;
    final projection = canonical != null
        ? HomepageMarkdownDocumentAdapter.canonical(canonical)
        : HomepageMarkdownDocumentAdapter.legacy(markdown ?? '');
    if (!projection.isAvailable) {
      return Semantics(
        identifier: 'homepage_markdown_semantic_unavailable',
        child: Text(ObjectHomepageText.objectIntroEmptyMessage),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        for (final block in projection.document!.blocks)
          _HomepageMarkdownBlock(block: block, assetsById: assetsById),
      ],
    );
  }
}

class _HomepageMarkdownBlock extends StatelessWidget {
  const _HomepageMarkdownBlock({required this.block, required this.assetsById});

  final QwqMarkdownBlock block;
  final Map<String, HomepageIntroductionAsset> assetsById;

  @override
  Widget build(BuildContext context) {
    final bodyStyle = TextStyle(
      fontSize: AppTypography.iosBody,
      height: AppTypography.lineHeightRelaxed,
      color: AppColors.iosLabel(context),
    );
    final child = switch (block.kind) {
      QwqMarkdownBlockKind.heading => Text(
        block.text,
        style: bodyStyle.copyWith(
          fontSize: block.level <= 1
              ? AppTypography.iosTitle2
              : AppTypography.iosTitle3,
          fontWeight: AppTypography.semiBold,
        ),
      ),
      QwqMarkdownBlockKind.orderedItem => _HomepageListItem(
        marker: '${block.id.split('_').last}.',
        text: block.text,
        depth: block.listDepth,
      ),
      QwqMarkdownBlockKind.bulletItem => _HomepageListItem(
        marker: '•',
        text: block.text,
        depth: block.listDepth,
      ),
      QwqMarkdownBlockKind.quote => DecoratedBox(
        decoration: BoxDecoration(
          border: Border(left: BorderSide(color: AppColors.primaryColor)),
        ),
        child: Padding(
          padding: EdgeInsets.only(left: AppSpacing.containerXs),
          child: Text(block.text, style: bodyStyle),
        ),
      ),
      QwqMarkdownBlockKind.codeBlock => DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosFill(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerXs),
          child: SelectableText(
            block.text,
            style: bodyStyle.copyWith(fontFamily: 'monospace'),
          ),
        ),
      ),
      QwqMarkdownBlockKind.figure ||
      QwqMarkdownBlockKind.image => _HomepageSemanticFigure(
        assetRef: block.assetRef,
        assetsById: assetsById,
      ),
      QwqMarkdownBlockKind.gallery => Wrap(
        spacing: AppSpacing.containerXs,
        runSpacing: AppSpacing.containerXs,
        children: <Widget>[
          for (final assetRef in block.assetRefs)
            SizedBox(
              width: _introHorizontalCardWidth,
              child: _HomepageSemanticFigure(
                assetRef: assetRef,
                assetsById: assetsById,
              ),
            ),
        ],
      ),
      QwqMarkdownBlockKind.callout => DecoratedBox(
        decoration: BoxDecoration(
          color: AppColors.iosFill(context),
          borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
        ),
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerXs),
          child: Text(block.text, style: bodyStyle),
        ),
      ),
      QwqMarkdownBlockKind.table => Table(
        border: TableBorder.all(color: AppColors.iosSeparator(context)),
        children: <TableRow>[
          for (final row in block.table?.logicalGrid ?? const <List<String>>[])
            TableRow(
              children: <Widget>[
                for (final cell in row)
                  Padding(
                    padding: EdgeInsets.all(AppSpacing.intraGroupXs),
                    child: Text(cell, style: bodyStyle),
                  ),
              ],
            ),
        ],
      ),
      QwqMarkdownBlockKind.groupedDirectory => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (final group
              in block.groupedDirectory?.groups.entries ??
                  const <MapEntry<String, List<String>>>[]) ...<Widget>[
            Text(
              group.key,
              style: bodyStyle.copyWith(fontWeight: AppTypography.semiBold),
            ),
            for (final item in group.value)
              _HomepageListItem(marker: '•', text: item, depth: 0),
          ],
        ],
      ),
      QwqMarkdownBlockKind.definitionList => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          for (final definition in block.definitions) ...<Widget>[
            Text(
              definition.term,
              style: bodyStyle.copyWith(fontWeight: AppTypography.semiBold),
            ),
            Text(definition.definition, style: bodyStyle),
          ],
        ],
      ),
      QwqMarkdownBlockKind.footnote => Text(
        '[${block.footnote?.label ?? ''}] ${block.footnote?.text ?? block.text}',
        style: bodyStyle.copyWith(fontSize: AppTypography.iosFootnote),
      ),
      QwqMarkdownBlockKind.horizontalRule => Divider(
        color: AppColors.iosSeparator(context),
      ),
      QwqMarkdownBlockKind.spacer => SizedBox(height: AppSpacing.containerSm),
      QwqMarkdownBlockKind.paragraph ||
      QwqMarkdownBlockKind.card ||
      QwqMarkdownBlockKind.section => Text(block.text, style: bodyStyle),
      QwqMarkdownBlockKind.unsupported => Semantics(
        identifier: 'homepage_markdown_node_unavailable',
        child: Text(
          ObjectHomepageText.objectIntroEmptyMessage,
          style: bodyStyle,
        ),
      ),
    };
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
      child: child,
    );
  }
}

class _HomepageListItem extends StatelessWidget {
  const _HomepageListItem({
    required this.marker,
    required this.text,
    required this.depth,
  });

  final String marker;
  final String text;
  final int depth;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.only(left: depth * AppSpacing.containerSm),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        SizedBox(width: AppSpacing.containerSm, child: Text(marker)),
        Expanded(child: Text(text)),
      ],
    ),
  );
}

class _HomepageSemanticFigure extends StatelessWidget {
  const _HomepageSemanticFigure({
    required this.assetRef,
    required this.assetsById,
  });

  final QwqMarkdownAssetRef? assetRef;
  final Map<String, HomepageIntroductionAsset> assetsById;

  @override
  Widget build(BuildContext context) {
    final ref = assetRef;
    final asset = ref == null ? null : assetsById[ref.assetId];
    if (asset == null ||
        (asset.url.trim().isEmpty && !_declaresSignedGrantIntroAsset(asset))) {
      return Semantics(
        identifier: 'homepage_markdown_asset_unavailable',
        child: Text(ObjectHomepageText.objectIntroEmptyMessage),
      );
    }
    return _InlineFigure(asset: asset, caption: ref!.caption);
  }
}

/// 三段结构正文块级内嵌图：上图下文、不环绕、仅单行原图注。
class _InlineFigure extends StatelessWidget {
  const _InlineFigure({required this.asset, required this.caption});

  final HomepageIntroductionAsset asset;
  final String caption;

  @override
  Widget build(BuildContext context) {
    final effectiveCaption = caption.isNotEmpty
        ? caption
        : (asset.caption ?? '').trim();
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
            child: AspectRatio(
              aspectRatio: _introInlineFigureAspectRatio,
              child: mediaDeliveryImage(
                binding: MediaDeliveryBinding(
                  assetId: asset.assetId.trim(),
                  accessMode: asset.accessMode,
                  publicUrl: asset.url,
                ),
                kind: MediaDeliveryKind.image,
                fit: BoxFit.cover,
                placeholder: ColoredBox(color: AppColors.iosFill(context)),
                absentWidget: ColoredBox(color: AppColors.iosFill(context)),
                publicBuilder: (context, publicUrl) => AppMediaImage(
                  imageSource: publicUrl,
                  fit: BoxFit.cover,
                  placeholder: ColoredBox(color: AppColors.iosFill(context)),
                  errorWidget: ColoredBox(color: AppColors.iosFill(context)),
                ),
              ),
            ),
          ),
          if (effectiveCaption.isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              effectiveCaption,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _TimelineList extends StatelessWidget {
  const _TimelineList({required this.items});

  final List<HomepageIntroductionTimelineItem> items;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: items
          .map(
            (item) => Padding(
              padding: EdgeInsets.only(bottom: AppSpacing.containerXs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  SizedBox(
                    width: _introTimelineDateWidth,
                    child: Text(
                      item.dateLabel,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        fontWeight: AppTypography.semiBold,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ),
                  Expanded(
                    child: Text(
                      item.text,
                      style: TextStyle(
                        fontSize: AppTypography.iosBody,
                        height: AppTypography.lineHeightRelaxed,
                        color: AppColors.iosLabel(context),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          )
          .toList(growable: false),
    );
  }
}

class _AssetStrip extends StatelessWidget {
  const _AssetStrip({required this.assets});

  final List<HomepageIntroductionAsset> assets;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: _introAssetStripHeight,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: assets.length,
        separatorBuilder: (_, _) => SizedBox(width: AppSpacing.containerXs),
        itemBuilder: (context, index) {
          final asset = assets[index];
          return SizedBox(
            width: _introHorizontalCardWidth,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  // DEC-033：走唯一 typed 分流入口，不在消费点手写第二份
                  // 「什么算私有」的判据。
                  mediaDeliveryImage(
                    binding: MediaDeliveryBinding(
                      assetId: asset.assetId.trim(),
                      accessMode: asset.accessMode,
                      publicUrl: asset.url,
                    ),
                    kind: MediaDeliveryKind.image,
                    fit: BoxFit.cover,
                    placeholder: ColoredBox(color: AppColors.iosFill(context)),
                    absentWidget: ColoredBox(color: AppColors.iosFill(context)),
                    publicBuilder: (context, publicUrl) => AppMediaImage(
                      imageSource: publicUrl,
                      fit: BoxFit.cover,
                      placeholder: ColoredBox(
                        color: AppColors.iosFill(context),
                      ),
                      errorWidget: ColoredBox(
                        color: AppColors.iosFill(context),
                      ),
                    ),
                  ),
                  if ((asset.caption ?? '').trim().isNotEmpty)
                    Positioned(
                      left: AppSpacing.containerXs,
                      right: AppSpacing.containerXs,
                      bottom: AppSpacing.containerXs,
                      child: Text(
                        asset.caption!.trim(),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: CupertinoColors.white,
                          fontSize: AppTypography.iosCaption1,
                        ),
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
}
