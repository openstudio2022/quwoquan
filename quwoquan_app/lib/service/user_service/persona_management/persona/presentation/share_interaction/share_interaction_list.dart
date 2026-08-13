import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/feedback/skeleton/app_skeleton.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/runtime/di/profile_interaction_activity_dependencies.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_empty_state.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/presentation/share_interaction/share_interaction_row.dart';

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
          .read(shareInteractionTelemetryProvider)
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
    final state = ref.read(shareInteractionStateProvider(_bucketKey));
    ref
        .read(shareInteractionTelemetryProvider)
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
    final state = ref.watch(shareInteractionStateProvider(_bucketKey));
    if (state.isInitialLoading && state.items.isEmpty) {
      return const _ShareInteractionSkeletonList();
    }
    if (state.items.isEmpty) {
      if (state.error != null) {
        return AppSectionErrorState(
          semantic: ensureRetryUiErrorSemantic(
            runtimeErrorSemantic(
              context,
              error: state.error!,
              category: UiErrorCategory.sectionLoad,
              scope: UiErrorScope.section,
            ),
          ),
          onAction: (_) => _refresh(),
        );
      }
      return shareInteractionEmptyState(
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
            final current = ref.read(shareInteractionStateProvider(_bucketKey));
            if (current.isLoadingMore || !current.hasMore) return;
            ref
                .read(shareInteractionTelemetryProvider)
                .track(
                  eventName: ShareInteractionEventNames.loadMore,
                  personaId: widget.personaId,
                  direction: widget.direction,
                  itemCount: current.items.length,
                );
            unawaited(
              ref
                  .read(shareInteractionControllerProvider(_bucketKey))
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
          ref.read(shareInteractionControllerProvider(_bucketKey)).loadMore(),
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
        .read(shareInteractionTelemetryProvider)
        .track(
          eventName: ShareInteractionEventNames.refresh,
          personaId: widget.personaId,
          direction: widget.direction,
        );
    await ref.read(shareInteractionControllerProvider(_bucketKey)).refresh();
  }

  void _markImpression(ShareInteractionItem item) {
    ref
        .read(shareInteractionTelemetryProvider)
        .track(
          eventName: ShareInteractionEventNames.impression,
          personaId: widget.personaId,
          direction: widget.direction,
          item: item,
        );
    unawaited(
      ref
          .read(shareInteractionControllerProvider(_bucketKey))
          .markSeen(item.interactionId),
    );
  }

  void _openUser(ShareInteractionItem item) {
    final userId = item.displayPersonaId.trim();
    if (userId.isEmpty) return;
    ref
        .read(shareInteractionTelemetryProvider)
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
        avatarUrl: item.displayAvatarUrl.isEmpty ? null : item.displayAvatarUrl,
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
        .read(shareInteractionTelemetryProvider)
        .track(
          eventName: ShareInteractionEventNames.open,
          personaId: widget.personaId,
          direction: widget.direction,
          item: item,
        );
    unawaited(
      ref
          .read(shareInteractionControllerProvider(_bucketKey))
          .markRead(item.interactionId),
    );
    context.push(
      AppRoutePaths.workBrowser(
        workId: objectId,
        filter: _targetFilter(item.targetContentType),
        source: ShareInteractionTelemetry.source,
      ),
    );
  }

  void _openImpact(ShareInteractionItem item) {
    if (item.impactDeepLink != 'myIntersections') return;
    ref
        .read(shareInteractionTelemetryProvider)
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
    // 行形状：头像位 + 两行文字条 + 预览缩略位；脉动由统一 primitives 承载。
    Widget bar(double widthFactor) => FractionallySizedBox(
      widthFactor: widthFactor,
      child: const AppSkeletonLine(height: AppSpacing.sm),
    );
    return AppSkeletonShimmer(
      child: Column(
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
                  const AppSkeletonCircle(
                    size: AppSpacing.profileShareInteractionAvatarSize,
                  ),
                  SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        bar(0.4),
                        SizedBox(height: AppSpacing.xs),
                        bar(0.8),
                      ],
                    ),
                  ),
                  SizedBox(width: AppSpacing.sm),
                  const AppSkeletonBlock(
                    width: AppSpacing.profileShareInteractionPreviewSize,
                    height: AppSpacing.profileShareInteractionPreviewSize,
                  ),
                ],
              ),
            ),
          ),
        ),
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
