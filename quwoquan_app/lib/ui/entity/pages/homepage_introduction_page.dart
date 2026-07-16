import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_asset.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_section.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_introduction_timeline_item.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_related_group_summary.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_source.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/ui/entity/providers/homepage_introduction_provider.dart';
import 'package:url_launcher/url_launcher.dart';

const double _introHeroHeight = AppSpacing.twoHundredTwenty;
const double _introTimelineDateWidth = 86.0;
const double _introAssetStripHeight = AppSpacing.commentComposerMaxHeight;
const double _introHorizontalCardWidth = 180.0;
const double _introRelatedObjectHeight = AppSpacing.homeObjectCardRailHeight;

/// 正文块级内嵌图（三段结构 role=inline）统一横图比例。
const double _introInlineFigureAspectRatio = 16 / 9;

class HomepageIntroductionPage extends ConsumerStatefulWidget {
  const HomepageIntroductionPage({
    super.key,
    required this.homepageId,
    this.referralSource = ReferralSource.entityPage,
  });

  final String homepageId;
  final ReferralSource referralSource;

  @override
  ConsumerState<HomepageIntroductionPage> createState() =>
      _HomepageIntroductionPageState();
}

class _HomepageIntroductionPageState
    extends ConsumerState<HomepageIntroductionPage> {
  final ScrollController _scrollController = ScrollController();
  final DateTime _enteredAt = DateTime.now();
  double _maxDepth = 0;
  late final JourneyEventTracker _journeyTracker;

  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _scrollController.addListener(_trackDepth);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackJourney('enter', payload: _basePayload());
    });
  }

  @override
  void dispose() {
    _scrollController.removeListener(_trackDepth);
    _trackJourney(
      'exit',
      payload: <String, dynamic>{
        ..._basePayload(),
        'durationMs': DateTime.now().difference(_enteredAt).inMilliseconds,
        'maxDepth': _maxDepth,
      },
    );
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final asyncValue = ref.watch(
      homepageIntroductionProvider(widget.homepageId),
    );
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      backgroundColor: SettingsSemanticConstants.pageBackground(isDark),
      navigationBar: CupertinoNavigationBar(
        middle: const Text('认识'),
        leading: CupertinoButton(
          padding: EdgeInsets.zero,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.homepageDetail(id: widget.homepageId));
            }
          },
          child: const Icon(CupertinoIcons.chevron_back),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: asyncValue.when(
          loading: () => const Center(child: CupertinoActivityIndicator()),
          error: (error, _) => AppSectionErrorCard(
            semantic: runtimeErrorSemantic(
              context,
              error: error,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
            ),
            onAction: (action) {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                ref.invalidate(homepageIntroductionProvider(widget.homepageId));
              }
              return Future<void>.value();
            },
          ),
          data: (introduction) {
            if (introduction == null ||
                introduction.summary.trim().isEmpty ||
                introduction.sections.isEmpty) {
              return _IntroductionEmptyState(
                onBack: () {
                  context.go(
                    AppRoutePaths.homepageDetail(id: widget.homepageId),
                  );
                },
              );
            }
            return _buildContent(context, introduction);
          },
        ),
      ),
    );
  }

  Widget _buildContent(
    BuildContext context,
    HomepageIntroduction introduction,
  ) {
    final title = introduction.displayName.trim().isEmpty
        ? widget.homepageId
        : introduction.displayName.trim();
    return ListView(
      controller: _scrollController,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        AppSpacing.containerXl,
      ),
      children: <Widget>[
        _IntroductionHero(introduction: introduction),
        SizedBox(height: AppSpacing.containerSm),
        _IntroductionCard(
          child: Text(
            introduction.summary,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              height: AppTypography.lineHeightRelaxed,
              color: AppColors.iosLabel(context),
            ),
          ),
        ),
        for (final section in introduction.sections) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _IntroductionSectionCard(section: section),
        ],
        if (introduction.relatedObjects.isNotEmpty) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _RelatedObjectsSection(
            items: introduction.relatedObjects,
            onTap: (item) {
              _trackJourney(
                'related_object_click',
                targetKey: item.linkedHomepageId ?? item.circleId,
                payload: _basePayload(),
              );
              final target = (item.linkedHomepageId ?? '').trim();
              if (target.isNotEmpty) {
                context.push(AppRoutePaths.homepageDetail(id: target));
              }
            },
          ),
        ],
        SizedBox(height: AppSpacing.containerSm),
        _ReturnLinksCard(
          title: title,
          onTap: (target) {
            _trackJourney(
              'return_link_click',
              targetKey: target,
              payload: _basePayload(),
            );
            context.go(AppRoutePaths.homepageDetail(id: widget.homepageId));
          },
        ),
        if (introduction.primarySource != null) ...<Widget>[
          SizedBox(height: AppSpacing.containerSm),
          _HomepageSourceCard(source: introduction.primarySource!),
        ],
      ],
    );
  }

  void _trackDepth() {
    if (!_scrollController.hasClients) {
      return;
    }
    final maxExtent = _scrollController.position.maxScrollExtent;
    final depth = maxExtent <= 0
        ? 1.0
        : (_scrollController.offset / maxExtent).clamp(0.0, 1.0);
    if (depth > _maxDepth) {
      _maxDepth = depth;
    }
  }

  Map<String, dynamic> _basePayload() {
    return <String, dynamic>{
      'homepageId': widget.homepageId,
      'referralSource': widget.referralSource.value,
    };
  }

  void _trackJourney(
    String action, {
    String targetKey = '',
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) {
    unawaited(
      _journeyTracker.trackAction(
        journey: 'homepage_introduction',
        action: action,
        pageName: 'homepage_introduction',
        targetType: targetKey.isEmpty ? '' : 'homepage',
        targetKey: targetKey,
        entityType: 'homepage',
        entityId: widget.homepageId,
        payload: payload,
      ),
    );
  }
}

class _IntroductionHero extends StatelessWidget {
  const _IntroductionHero({required this.introduction});

  final HomepageIntroduction introduction;

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
            if (coverUrl.isNotEmpty)
              AppMediaImage(
                imageSource: coverUrl,
                fit: BoxFit.cover,
                placeholder: const SizedBox.shrink(),
                errorWidget: const SizedBox.shrink(),
              ),
            DecoratedBox(
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
                    _typeLabel(introduction.homepageType),
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
        if (asset != null && asset.url.trim().isNotEmpty) {
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
              child: AppMediaImage(
                imageSource: asset.url,
                fit: BoxFit.cover,
                placeholder: ColoredBox(color: AppColors.iosFill(context)),
                errorWidget: ColoredBox(color: AppColors.iosFill(context)),
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
                  AppMediaImage(
                    imageSource: asset.url,
                    fit: BoxFit.cover,
                    placeholder: ColoredBox(color: AppColors.iosFill(context)),
                    errorWidget: ColoredBox(color: AppColors.iosFill(context)),
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

class _RelatedObjectsSection extends StatelessWidget {
  const _RelatedObjectsSection({required this.items, required this.onTap});

  final List<HomepageRelatedGroupSummary> items;
  final ValueChanged<HomepageRelatedGroupSummary> onTap;

  @override
  Widget build(BuildContext context) {
    return _IntroductionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            '相关地点和事物',
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          SizedBox(
            height: _introRelatedObjectHeight,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: items.length,
              separatorBuilder: (_, _) =>
                  SizedBox(width: AppSpacing.containerXs),
              itemBuilder: (context, index) {
                final item = items[index];
                return CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: () => onTap(item),
                  child: Container(
                    width: _introHorizontalCardWidth,
                    padding: EdgeInsets.all(AppSpacing.containerSm),
                    decoration: BoxDecoration(
                      color: AppColors.iosGroupedSurfaceElevated(context),
                      borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: <Widget>[
                        Text(
                          item.linkedHomepageTitle ?? item.name,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosBody,
                            fontWeight: AppTypography.semiBold,
                            color: AppColors.iosLabel(context),
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupXs),
                        Text(
                          item.memberCount > 0
                              ? '${item.memberCount} 人讨论'
                              : '查看主页',
                          style: TextStyle(
                            fontSize: AppTypography.iosFootnote,
                            color: AppColors.iosSecondaryLabel(context),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _ReturnLinksCard extends StatelessWidget {
  const _ReturnLinksCard({required this.title, required this.onTap});

  final String title;
  final ValueChanged<String> onTap;

  @override
  Widget build(BuildContext context) {
    return _IntroductionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            '继续了解 $title',
            style: TextStyle(
              fontSize: AppTypography.iosTitle3,
              fontWeight: AppTypography.semiBold,
              color: AppColors.iosLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.containerSm),
          Wrap(
            spacing: AppSpacing.intraGroupSm,
            runSpacing: AppSpacing.intraGroupSm,
            children: <Widget>[
              _ReturnChip(label: '看记录', onTap: () => onTap('content')),
              _ReturnChip(label: '看讨论', onTap: () => onTap('discussion')),
              _ReturnChip(label: '找相关圈子', onTap: () => onTap('circle')),
            ],
          ),
        ],
      ),
    );
  }
}

class _ReturnChip extends StatelessWidget {
  const _ReturnChip({required this.label, required this.onTap});

  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      color: AppColors.primaryColor.withValues(alpha: 0.12),
      borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
      onPressed: onTap,
      child: Text(
        label,
        style: const TextStyle(
          color: AppColors.primaryColor,
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }
}

class _HomepageSourceCard extends StatelessWidget {
  const _HomepageSourceCard({required this.source});

  final HomepageSource source;

  Uri? get _safeUri {
    final uri = Uri.tryParse(source.sourceUrl.trim());
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        !_isPublicSourceHost(uri.host) ||
        uri.queryParameters.keys.any(_isSensitiveSourceQueryKey)) {
      return null;
    }
    return uri;
  }

  @override
  Widget build(BuildContext context) {
    final uri = _safeUri;
    final host = uri?.host ?? '';
    return _IntroductionCard(
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: uri == null
            ? null
            : () {
                unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
              },
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    UITextConstants.objectIntroSourceTitle,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    source.title.trim().isEmpty
                        ? UITextConstants.objectIntroSourcePlatform(
                            source.sourceKind,
                          )
                        : source.title.trim(),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  if (host.isNotEmpty)
                    Text(
                      '${UITextConstants.objectIntroSourcePlatform(source.sourceKind)} · $host',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: AppColors.iosTertiaryLabel(context),
                      ),
                    ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.arrow_up_right_square,
              size: AppSpacing.iconMedium,
              color: AppColors.iosSecondaryLabel(context),
              semanticLabel: UITextConstants.objectIntroSourceOpen,
            ),
          ],
        ),
      ),
    );
  }
}

bool _isPublicSourceHost(String rawHost) {
  final host = rawHost.toLowerCase();
  if (host == 'localhost' ||
      host == '::1' ||
      host.endsWith('.local') ||
      host.startsWith('127.') ||
      host.startsWith('10.') ||
      host.startsWith('192.168.')) {
    return false;
  }
  final parts = host.split('.');
  if (parts.length == 4 && parts.first == '172') {
    final second = int.tryParse(parts[1]);
    if (second != null && second >= 16 && second <= 31) {
      return false;
    }
  }
  return true;
}

bool _isSensitiveSourceQueryKey(String rawKey) {
  final key = rawKey.toLowerCase();
  return key.contains('token') ||
      key.contains('signature') ||
      key.contains('credential') ||
      key.contains('auth');
}

class _IntroductionEmptyState extends StatelessWidget {
  const _IntroductionEmptyState({required this.onBack});

  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.doc_text_search,
              size: AppSpacing.iconLarge,
              color: AppColors.iosSecondaryLabel(context),
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              '介绍正在整理中',
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              '先回到主页查看相关内容和讨论。',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.containerMd),
            CupertinoButton.filled(
              onPressed: onBack,
              child: const Text('回到主页'),
            ),
          ],
        ),
      ),
    );
  }
}

class _IntroductionCard extends StatelessWidget {
  const _IntroductionCard({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: AppColors.iosProfileSurface(context),
        borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
        border: Border.all(
          color: AppColors.iosSeparator(context).withValues(alpha: 0.12),
          width: AppSpacing.hairline,
        ),
      ),
      child: child,
    );
  }
}

String _typeLabel(String homepageType) {
  return switch (homepageType) {
    'sight' => '地点',
    'travel_photo' => '旅行摄影',
    'hotel' => '住宿',
    'restaurant' => '餐饮',
    'university' => '校园',
    _ => '主页',
  };
}
