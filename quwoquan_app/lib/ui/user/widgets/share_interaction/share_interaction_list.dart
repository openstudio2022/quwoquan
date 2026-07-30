import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/share_interaction_observability.dart';
import 'package:quwoquan_app/ui/user/models/share_interaction_models.dart';
import 'package:quwoquan_app/ui/user/providers/share_interaction_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_empty_state.dart';
import 'package:quwoquan_app/ui/user/widgets/share_interaction/share_interaction_row.dart';

class ShareInteractionList extends ConsumerStatefulWidget {
  const ShareInteractionList({
    super.key,
    required this.direction,
    required this.personaId,
    this.inlineScroll = false,
  });

  final ShareInteractionDirection direction;
  final String personaId;
  final bool inlineScroll;

  @override
  ConsumerState<ShareInteractionList> createState() =>
      _ShareInteractionListState();
}

class _ShareInteractionListState extends ConsumerState<ShareInteractionList> {
  ShareInteractionBucketKey get _bucketKey => ShareInteractionBucketKey(
    personaId: widget.personaId,
    direction: widget.direction,
  );

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _trackView());
  }

  @override
  void didUpdateWidget(covariant ShareInteractionList oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.direction != widget.direction) {
      ref
          .read(shareInteractionObservabilityProvider)
          .track(
            eventName: ShareInteractionEventNames.directionChange,
            personaId: widget.personaId,
            direction: widget.direction,
          );
      WidgetsBinding.instance.addPostFrameCallback((_) => _trackView());
    }
  }

  void _trackView() {
    if (!mounted) return;
    final state = ref.read(shareInteractionProvider(_bucketKey));
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.view,
          personaId: widget.personaId,
          direction: widget.direction,
          cacheHit: state.hasCachedItems,
          itemCount: state.items.length,
        );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(shareInteractionProvider(_bucketKey));
    if (state.isInitialLoading && state.items.isEmpty) {
      return const _ShareInteractionSkeletonList();
    }
    if (state.items.isEmpty) {
      if (state.error != null) {
        return _InitialErrorState(onRetry: _refresh);
      }
      return ShareEmptyState(
        direction: widget.direction,
        onAction: () {
          if (widget.direction == ShareInteractionDirection.received) {
            context.push(AppRoutePaths.create());
          } else {
            context.go(AppRoutePaths.home);
          }
        },
      );
    }

    final entries = _groupedEntries(state.items);
    return ListView.builder(
      key: ValueKey<String>('share-interaction-list-${widget.direction.name}'),
      physics: widget.inlineScroll
          ? const NeverScrollableScrollPhysics()
          : const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
      shrinkWrap: widget.inlineScroll,
      padding: EdgeInsets.only(bottom: AppSpacing.containerMd),
      itemCount: entries.length + 1,
      itemBuilder: (context, index) {
        if (index == entries.length) {
          return _buildFooter(state);
        }
        final entry = entries[index];
        if (entry.group != null) {
          return _GroupHeader(group: entry.group!);
        }
        final item = entry.item!;
        final sourceIndex = state.items.indexOf(item);
        if (sourceIndex >= state.items.length - 5 && state.hasMore) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (!mounted) return;
            final current = ref.read(shareInteractionProvider(_bucketKey));
            if (current.isLoadingMore || !current.hasMore) return;
            ref
                .read(shareInteractionObservabilityProvider)
                .track(
                  eventName: ShareInteractionEventNames.loadMore,
                  personaId: widget.personaId,
                  direction: widget.direction,
                  itemCount: current.items.length,
                );
            unawaited(
              ref
                  .read(shareInteractionProvider(_bucketKey).notifier)
                  .loadMore(),
            );
          });
        }
        return _ShareVisibilityTracker(
          key: ValueKey<String>('share-visible-${item.interactionId}'),
          onQualified: () => _markImpression(item),
          child: ShareInteractionRow(
            item: item,
            isLast: _isLastItem(entries, index),
            onOpenUser: () => _openUser(item),
            onOpenTarget:
                item.targetNavigationResolution !=
                    ShareTargetNavigationResolution.unavailable
                ? () => _openTarget(item)
                : null,
            onOpenImpact: item.impactIsNavigable
                ? () => _openImpact(item)
                : null,
          ),
        );
      },
    );
  }

  Widget _buildFooter(ShareInteractionState state) {
    if (state.isLoadingMore) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            AppRequestFeedback.inline(),
            SizedBox(width: AppSpacing.xs),
            Text(ProfileText.profileShareLoading),
          ],
        ),
      );
    }
    if (state.error != null) {
      return CupertinoButton(
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: () => unawaited(
          ref.read(shareInteractionProvider(_bucketKey).notifier).loadMore(),
        ),
        child: Text(ProfileText.profileShareLoadFailed),
      );
    }
    if (!state.hasMore) {
      return Padding(
        padding: EdgeInsets.all(AppSpacing.md),
        child: Text(
          ProfileText.profileShareNoMore,
          textAlign: TextAlign.center,
          style: TextStyle(
            color: AppColors.iosSecondaryLabel(context),
            fontSize: AppTypography.iosCaption1,
          ),
        ),
      );
    }
    return const SizedBox.shrink();
  }

  Future<void> _refresh() async {
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.refresh,
          personaId: widget.personaId,
          direction: widget.direction,
        );
    await ref.read(shareInteractionProvider(_bucketKey).notifier).refresh();
  }

  void _markImpression(ShareInteractionItem item) {
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.impression,
          personaId: widget.personaId,
          direction: widget.direction,
          item: item,
        );
    unawaited(
      ref
          .read(shareInteractionProvider(_bucketKey).notifier)
          .markSeen(item.interactionId),
    );
  }

  void _openUser(ShareInteractionItem item) {
    final userId = item.displayPersonaId.trim();
    if (userId.isEmpty) return;
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.actorOpen,
          personaId: widget.personaId,
          direction: widget.direction,
          item: item,
        );
    context.push(
      AppRoutePaths.userProfile(userHandle: userId),
      extra: UserProfileRouteExtra(
        personaId: userId,
        avatar: item.displayAvatarUrl.isEmpty ? null : item.displayAvatarUrl,
        displayName: item.displayName.isEmpty ? null : item.displayName,
      ),
    );
  }

  void _openTarget(ShareInteractionItem item) {
    final objectId = switch (item.targetNavigationResolution) {
      ShareTargetNavigationResolution.originalTarget => item.targetContentId,
      ShareTargetNavigationResolution.unavailable => '',
    };
    if (objectId.isEmpty) return;
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.open,
          personaId: widget.personaId,
          direction: widget.direction,
          item: item,
        );
    unawaited(
      ref
          .read(shareInteractionProvider(_bucketKey).notifier)
          .markRead(item.interactionId),
    );
    context.push(
      AppRoutePaths.workBrowser(
        workId: objectId,
        filter: _targetFilter(item.targetContentType),
        source: ShareInteractionObservability.source,
      ),
    );
  }

  void _openImpact(ShareInteractionItem item) {
    if (item.impactDeepLink != 'myIntersections') return;
    ref
        .read(shareInteractionObservabilityProvider)
        .track(
          eventName: ShareInteractionEventNames.impactOpen,
          personaId: widget.personaId,
          direction: widget.direction,
          item: item,
          result: 'opened',
        );
    context.push(
      AppRoutePaths.myIntersections(
        sourceRef: item.interactionId,
        filter: 'impact',
      ),
    );
  }
}

class _ShareListEntry {
  const _ShareListEntry.group(this.group) : item = null;
  const _ShareListEntry.item(this.item) : group = null;

  final ShareInteractionDateGroup? group;
  final ShareInteractionItem? item;
}

List<_ShareListEntry> _groupedEntries(List<ShareInteractionItem> items) {
  final entries = <_ShareListEntry>[];
  ShareInteractionDateGroup? previous;
  final now = DateTime.now();
  for (final item in items) {
    final group = shareInteractionDateGroup(item.occurredAt, now);
    if (group != previous) {
      entries.add(_ShareListEntry.group(group));
      previous = group;
    }
    entries.add(_ShareListEntry.item(item));
  }
  return entries;
}

bool _isLastItem(List<_ShareListEntry> entries, int index) {
  for (var next = index + 1; next < entries.length; next++) {
    if (entries[next].item != null) return false;
  }
  return true;
}

class _GroupHeader extends StatelessWidget {
  const _GroupHeader({required this.group});

  final ShareInteractionDateGroup group;

  @override
  Widget build(BuildContext context) {
    final text = switch (group) {
      ShareInteractionDateGroup.today => ProfileText.profileShareToday,
      ShareInteractionDateGroup.yesterday => ProfileText.profileShareYesterday,
      ShareInteractionDateGroup.older => ProfileText.profileShareOlder,
    };
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.md,
        AppSpacing.containerMd,
        AppSpacing.xs,
      ),
      child: Text(
        text,
        style: TextStyle(
          color: AppColors.iosSecondaryLabel(context),
          fontSize: AppTypography.iosCaption1,
          fontWeight: AppTypography.secondaryTabSelectedWeight,
        ),
      ),
    );
  }
}

class _ShareInteractionSkeletonList extends StatelessWidget {
  const _ShareInteractionSkeletonList();

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    final color = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    return Column(
      children: List<Widget>.generate(
        4,
        (index) => ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: AppSpacing.profileShareInteractionRowMinHeight,
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerMd,
              vertical: AppSpacing.md,
            ),
            child: Row(
              children: <Widget>[
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: color,
                    shape: BoxShape.circle,
                  ),
                  child: const SizedBox.square(
                    dimension: AppSpacing.profileShareInteractionAvatarSize,
                  ),
                ),
                SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      _SkeletonBar(color: color, widthFactor: 0.4),
                      SizedBox(height: AppSpacing.xs),
                      _SkeletonBar(color: color, widthFactor: 0.8),
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.sm),
                DecoratedBox(
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                  ),
                  child: const SizedBox.square(
                    dimension: AppSpacing.profileShareInteractionPreviewSize,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _SkeletonBar extends StatelessWidget {
  const _SkeletonBar({required this.color, required this.widthFactor});

  final Color color;
  final double widthFactor;

  @override
  Widget build(BuildContext context) {
    return FractionallySizedBox(
      widthFactor: widthFactor,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
        ),
        child: SizedBox(height: AppSpacing.sm),
      ),
    );
  }
}

class _InitialErrorState extends StatelessWidget {
  const _InitialErrorState({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: CupertinoButton(
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: onRetry,
        child: Text(ProfileText.profileShareLoadFailed),
      ),
    );
  }
}

class _ShareVisibilityTracker extends StatefulWidget {
  const _ShareVisibilityTracker({
    super.key,
    required this.child,
    required this.onQualified,
  });

  final Widget child;
  final VoidCallback onQualified;

  @override
  State<_ShareVisibilityTracker> createState() =>
      _ShareVisibilityTrackerState();
}

class _ShareVisibilityTrackerState extends State<_ShareVisibilityTracker> {
  ScrollPosition? _position;
  Timer? _timer;
  bool _reported = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final next = Scrollable.maybeOf(context)?.position;
    if (identical(next, _position)) return;
    _position?.removeListener(_evaluate);
    _position = next?..addListener(_evaluate);
    WidgetsBinding.instance.addPostFrameCallback((_) => _evaluate());
  }

  @override
  void dispose() {
    _position?.removeListener(_evaluate);
    _timer?.cancel();
    super.dispose();
  }

  void _evaluate() {
    if (!mounted || _reported) return;
    final box = context.findRenderObject();
    final scrollableBox = Scrollable.maybeOf(
      context,
    )?.context.findRenderObject();
    if (box is! RenderBox ||
        scrollableBox is! RenderBox ||
        !box.attached ||
        !scrollableBox.attached ||
        box.size.height <= 0) {
      _timer?.cancel();
      _timer = null;
      return;
    }
    final rowTop = box.localToGlobal(Offset.zero).dy;
    final rowBottom = rowTop + box.size.height;
    final viewportTop = scrollableBox.localToGlobal(Offset.zero).dy;
    final viewportBottom = viewportTop + scrollableBox.size.height;
    final visibleHeight =
        math.min(rowBottom, viewportBottom) - math.max(rowTop, viewportTop);
    final fraction = math.max(0, visibleHeight) / box.size.height;
    if (fraction < 0.5) {
      _timer?.cancel();
      _timer = null;
      return;
    }
    _timer ??= Timer(const Duration(seconds: 1), () {
      if (!mounted || _reported) return;
      _reported = true;
      widget.onQualified();
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

String? _targetFilter(String contentType) {
  return switch (contentType.trim()) {
    'image' || 'photo' => 'images',
    'video' => 'videos',
    'article' || 'text' => 'articles',
    _ => null,
  };
}
