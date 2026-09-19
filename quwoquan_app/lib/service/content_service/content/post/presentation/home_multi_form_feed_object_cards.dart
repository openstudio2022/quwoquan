part of 'home_multi_form_feed.dart';

// 统一列表项：服务端在同一条有序列表里混排 post 与实体主页，端侧按信封
// `objectKind` 选投影、按 `openSurface` 导航。anchorIndex 由交付序位派生，
// 指示插入在 items[anchorIndex] 之前；未知项在解码边界已被隔离，不到这里。

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

  final ContentFeedObjectCard card;

  @override
  String get stableIdentity => homeFeedObjectCardEntryIdentity(
    objectKind: card.objectKind.wireName,
    objectId: card.objectId,
    anchorIndex: card.anchorIndex,
  );
}

/// 把实体主页项按 anchorIndex 还原回服务端交付序位（anchor 越界的项丢弃）。
List<_HomeFeedEntry> _weaveObjectCards(
  List<ContentPostViewData> posts,
  List<ContentFeedObjectCard> cards,
) {
  if (cards.isEmpty) {
    return <_HomeFeedEntry>[
      for (var i = 0; i < posts.length; i++) _HomeFeedPostEntry(posts[i], i),
    ];
  }
  final byAnchor = <int, List<ContentFeedObjectCard>>{};
  for (final card in cards) {
    if (card.anchorIndex < 0 || card.anchorIndex > posts.length) {
      continue;
    }
    byAnchor
        .putIfAbsent(card.anchorIndex, () => <ContentFeedObjectCard>[])
        .add(card);
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

/// Recommendation 统一可发现目标卡；只按 metadata target kind 导航，不按垂类分叉。
class _HomeDiscoverableTargetCard extends ConsumerWidget {
  const _HomeDiscoverableTargetCard({
    super.key,
    required this.card,
    required this.isDark,
    required this.channelId,
    required this.feedRequestId,
    required this.policyDigest,
  });

  final ContentFeedObjectCard card;
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
            contentType: card.objectKind.wireName,
            referralSource: ReferralSource.organicFeed,
            feedRequestId: feedRequestId,
            channelId: channelId,
            policyDigest: policyDigest,
          );
    });
    final surface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final subtitle = card.homepage.subtitle?.trim() ?? '';
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
                    card.homepage.title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: AppColors.iosLabel(context),
                    ),
                  ),
                  if (subtitle.isNotEmpty) ...<Widget>[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      subtitle,
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

  /// 只按云物化的 `openSurface` 导航；不按对象种类或内容类型再选一次目的地。
  void _openObject(BuildContext context, WidgetRef ref) {
    final path = ContentOpenSurfaceNavigation.canOpen(card.openSurface)
        ? ContentOpenSurfaceNavigation.pathFor(
            openSurface: card.openSurface,
            objectId: card.objectId,
            source: ReferralSource.organicFeed.value,
            sourceTheme: uiErrorAppearanceRouteValueFor(context),
          )
        : null;
    if (path == null) {
      unawaited(
        showContentPresentationUnsupportedTerminal(
          context,
          objectId: card.objectId,
          openSurface: card.openSurface,
        ),
      );
      return;
    }
    context.push(path);
    ref
        .read(contentBehaviorTrackerProvider)
        .trackClick(
          card.objectId,
          contentType: card.objectKind.wireName,
          referralSource: ReferralSource.organicFeed,
          feedRequestId: feedRequestId,
          channelId: channelId,
          policyDigest: policyDigest,
        );
  }
}
