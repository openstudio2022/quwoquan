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
          if ((section.bodyMarkdown ?? '').trim().isNotEmpty) ...<Widget>[
            SizedBox(height: AppSpacing.intraGroupSm),
            _MarkdownLite(
              markdown: section.bodyMarkdown!.trim(),
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

class _MarkdownLite extends StatelessWidget {
  const _MarkdownLite({
    required this.markdown,
    this.assetsById = const <String, HomepageIntroductionAsset>{},
  });

  final String markdown;

  /// 正文 `:::figure` 指令中 `asset://<assetId>` 的资产绑定（role=inline）。
  final Map<String, HomepageIntroductionAsset> assetsById;

  static final RegExp _figureCaptionRe = RegExp(r'caption="([^"]*)"');
  static final RegExp _assetRefRe = RegExp(r'^asset://(\S+)$');

  @override
  Widget build(BuildContext context) {
    final lines = markdown.split('\n');
    final widgets = <Widget>[];
    for (var i = 0; i < lines.length; i++) {
      final line = lines[i].trim();
      if (line.startsWith(':::figure')) {
        final caption =
            _figureCaptionRe.firstMatch(line)?.group(1)?.trim() ?? '';
        String assetId = '';
        var j = i + 1;
        for (; j < lines.length; j++) {
          final inner = lines[j].trim();
          if (inner == ':::') {
            break;
          }
          final assetMatch = _assetRefRe.firstMatch(inner);
          if (assetMatch != null) {
            assetId = assetMatch.group(1) ?? '';
          }
        }
        i = j;
        final asset = assetsById[assetId];
        // signedGrant 资产由 typed 绑定驱动渲染，不依赖 url 在场；
        // 公开资产维持既有 url 在场判定。
        if (asset != null &&
            (asset.url.trim().isNotEmpty ||
                _declaresSignedGrantIntroAsset(asset))) {
          widgets.add(_InlineFigure(asset: asset, caption: caption));
        }
        continue;
      }
      if (line.isEmpty) {
        widgets.add(SizedBox(height: AppSpacing.intraGroupXs));
        continue;
      }
      if (line.startsWith('- ')) {
        widgets.add(_BulletLine(text: line.substring(2).trim()));
      } else if (line.startsWith('#')) {
        widgets.add(
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.intraGroupXs),
            child: Text(
              line.replaceFirst(RegExp(r'^#+\s*'), ''),
              style: TextStyle(
                fontSize: AppTypography.iosNavTitle,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
          ),
        );
      } else {
        widgets.add(
          Text(
            line,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              height: AppTypography.lineHeightRelaxed,
              color: AppColors.iosLabel(context),
            ),
          ),
        );
      }
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: widgets,
    );
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
              // DEC-033：内嵌图经统一 typed 分流入口；私有与公开两路共用
              // 同一占位和失败体验，消费面不再手写 accessMode 三元判断。
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

class _BulletLine extends StatelessWidget {
  const _BulletLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text('• ', style: TextStyle(color: AppColors.iosLabel(context))),
          Expanded(
            child: Text(
              text,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                height: AppTypography.lineHeightRelaxed,
                color: AppColors.iosLabel(context),
              ),
            ),
          ),
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
