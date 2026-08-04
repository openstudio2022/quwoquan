part of 'home_multi_form_feed.dart';

// 混合对象卡（B4 阶段一插卡模式）：服务端随 feed envelope 下发 objectCards，
// anchorIndex 指示插入在 items[anchorIndex] 之前。本文件承载条目编织与实体
// 主页卡渲染；对象卡是增强位，缺失/异常时内容主体不受影响。

/// 首页 feed 展示条目：内容 post 或混合对象卡。
sealed class _HomeFeedEntry {
  const _HomeFeedEntry();

  String get stableIdentity;
}

final class _HomeFeedPostEntry extends _HomeFeedEntry {
  const _HomeFeedPostEntry(this.post, this.postIndex);

  final ContentPostViewData post;

  @override
  String get stableIdentity => homeFeedPostEntryIdentity(post.id);

  /// 数据索引（items 序位）：埋点 position 与 `home-feed-card-{index}` key
  /// 保持基于内容序位，不受对象卡插入影响。
  final int postIndex;
}

final class _HomeFeedObjectCardEntry extends _HomeFeedEntry {
  const _HomeFeedObjectCardEntry(this.card);

  final FeedObjectCard card;

  @override
  String get stableIdentity => homeFeedObjectCardEntryIdentity(
    objectKind: card.objectKind,
    objectId: card.objectId,
    anchorIndex: card.anchorIndex,
  );
}

/// 把对象卡按 anchorIndex 编织进内容序列（anchor 越界/非法的卡丢弃）。
List<_HomeFeedEntry> _weaveObjectCards(
  List<ContentPostViewData> posts,
  List<FeedObjectCard> cards,
) {
  if (cards.isEmpty) {
    return <_HomeFeedEntry>[
      for (var i = 0; i < posts.length; i++) _HomeFeedPostEntry(posts[i], i),
    ];
  }
  final byAnchor = <int, List<FeedObjectCard>>{};
  for (final card in cards) {
    if (card.objectId.trim().isEmpty || card.title.trim().isEmpty) {
      continue;
    }
    if (card.anchorIndex <= 0 || card.anchorIndex > posts.length) {
      continue;
    }
    byAnchor.putIfAbsent(card.anchorIndex, () => <FeedObjectCard>[]).add(card);
  }
  final entries = <_HomeFeedEntry>[];
  for (var i = 0; i < posts.length; i++) {
    final anchored = byAnchor[i];
    if (anchored != null) {
      entries.addAll(anchored.map(_HomeFeedObjectCardEntry.new));
    }
    entries.add(_HomeFeedPostEntry(posts[i], i));
  }
  final tailCards = byAnchor[posts.length];
  if (tailCards != null) {
    entries.addAll(tailCards.map(_HomeFeedObjectCardEntry.new));
  }
  return entries;
}

/// 实体主页对象卡（S0 唯一开启的 objectKind）。
class _HomeEntityObjectCard extends ConsumerWidget {
  const _HomeEntityObjectCard({
    super.key,
    required this.card,
    required this.isDark,
    required this.channelId,
    required this.feedRequestId,
    required this.policyDigest,
  });

  final FeedObjectCard card;
  final bool isDark;
  final String channelId;
  final String? feedRequestId;
  final String? policyDigest;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // 曝光归因：对象卡按 objectId/objectKind 走七态漏斗（visible 弱可见级）。
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref
          .read(contentBehaviorTrackerProvider)
          .trackVisible(
            card.objectId,
            contentType: card.objectKind,
            referralSource: ReferralSource.organicFeed,
            feedRequestId: feedRequestId,
            channelId: channelId,
            policyDigest: policyDigest,
            recallPath: card.recallPath,
          );
    });
    final surface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final displayTags = card.tagRefs
        .map(_entityCardTagLabel)
        .where((label) => label.isNotEmpty)
        .take(3)
        .toList(growable: false);
    return GestureDetector(
      key: ValueKey<String>('home-object-card-${card.objectId}'),
      behavior: HitTestBehavior.opaque,
      onTap: () => _openObject(context, ref),
      child: Container(
        color: surface,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.feedContentHorizontal(context),
          vertical: _feedCardVerticalPadding,
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.buttonHeight,
              height: AppSpacing.buttonHeight,
              decoration: BoxDecoration(
                color: AppColors.iosAccent(
                  context,
                ).withValues(alpha: isDark ? 0.24 : 0.12),
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
              ),
              alignment: Alignment.center,
              child: Icon(
                CupertinoIcons.map_pin_ellipse,
                size: AppSpacing.iconMedium,
                color: AppColors.iosAccent(context),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupMd),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    card.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  if (displayTags.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      displayTags.join(' · '),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosFootnote,
                        color: AppColors.iosSecondaryLabel(context),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.fourteen,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }

  void _openObject(BuildContext context, WidgetRef ref) {
    ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(
          card.objectId,
          contentType: card.objectKind,
          referralSource: ReferralSource.organicFeed,
          feedRequestId: feedRequestId,
          channelId: channelId,
          policyDigest: policyDigest,
          recallPath: card.recallPath,
        );
    // objectId 即可路由的 homepageId（服务端装配保证卡必可点）。
    context.push(AppRoutePaths.homepageDetail(id: card.objectId));
  }
}

/// 路径制 tagRef 的末段展示名（Topic/旅行/玩法/摄影旅拍 → 摄影旅拍）。
String _entityCardTagLabel(String tagRef) {
  final trimmed = tagRef.trim();
  if (trimmed.isEmpty) {
    return '';
  }
  final segments = trimmed.split('/');
  return segments.isEmpty ? '' : segments.last.trim();
}
