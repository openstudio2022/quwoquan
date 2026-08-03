import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_app/ui/travel/widgets/trip_item_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripTimelineBoard extends StatelessWidget {
  const TripTimelineBoard({
    super.key,
    required this.timeline,
    this.onOpenItem,
    this.onOpenPost,
    this.onManageMoment,
    this.manageableMomentIds = const <String>{},
  });

  final TripTimelineView timeline;
  final ValueChanged<String>? onOpenItem;
  final ValueChanged<String>? onOpenPost;
  final ValueChanged<String>? onManageMoment;
  final Set<String> manageableMomentIds;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Semantics(
      container: true,
      label: TravelText.timeline,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            TravelText.timeline,
            style: TextStyle(
              color: colors.onSurface,
              fontSize: AppTypography.sectionTitle,
              fontWeight: AppTypography.semiBold,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
          for (final day in timeline.days) ...[
            _TimelineDay(
              day: day,
              onOpenItem: onOpenItem,
              onOpenPost: onOpenPost,
              onManageMoment: onManageMoment,
              manageableMomentIds: manageableMomentIds,
            ),
            SizedBox(height: AppSpacing.interGroupMd),
          ],
        ],
      ),
    );
  }
}

final class _TimelineDay extends StatelessWidget {
  const _TimelineDay({
    required this.day,
    required this.onOpenItem,
    required this.onOpenPost,
    required this.onManageMoment,
    required this.manageableMomentIds,
  });

  final TripTimelineDaySlice day;
  final ValueChanged<String>? onOpenItem;
  final ValueChanged<String>? onOpenPost;
  final ValueChanged<String>? onManageMoment;
  final Set<String> manageableMomentIds;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  width: AppSpacing.minInteractiveSize,
                  height: AppSpacing.minInteractiveSize,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: colors.primaryContainer,
                    shape: BoxShape.circle,
                  ),
                  child: Text(
                    '${day.dayIndex}',
                    style: TextStyle(
                      color: colors.onPrimaryContainer,
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
                SizedBox(width: AppSpacing.containerSm),
                Expanded(
                  child: Text(
                    '${TravelText.dayPrefix}${day.dayIndex}${TravelText.daySuffix}',
                    style: TextStyle(
                      color: colors.onSurface,
                      fontSize: AppTypography.lg,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
                if (day.unassignedMoments.isNotEmpty)
                  _CountBadge(
                    icon: CupertinoIcons.photo_on_rectangle,
                    label:
                        '${TravelText.unassignedMoments} ${day.unassignedMoments.length}',
                  ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            if (day.items.isEmpty)
              Text(
                TravelText.noTimelineItems,
                style: TextStyle(
                  color: colors.onSurfaceVariant,
                  fontSize: AppTypography.body,
                ),
              )
            else
              for (final item in day.items)
                _TimelineItem(
                  item: item,
                  onOpenItem: onOpenItem,
                  onOpenPost: onOpenPost,
                  onManageMoment: onManageMoment,
                  manageableMomentIds: manageableMomentIds,
                ),
          ],
        ),
      ),
    );
  }
}

final class _TimelineItem extends StatelessWidget {
  const _TimelineItem({
    required this.item,
    required this.onOpenItem,
    required this.onOpenPost,
    required this.onManageMoment,
    required this.manageableMomentIds,
  });

  final TripTimelineItemSlice item;
  final ValueChanged<String>? onOpenItem;
  final ValueChanged<String>? onOpenPost;
  final ValueChanged<String>? onManageMoment;
  final Set<String> manageableMomentIds;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final time = item.startAt == null
        ? ''
        : MaterialLocalizations.of(
            context,
          ).formatTimeOfDay(TimeOfDay.fromDateTime(item.startAt!.toLocal()));
    return Semantics(
      button: onOpenItem != null,
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        onTap: onOpenItem == null ? null : () => onOpenItem!(item.itemId),
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                tripItemKindIcon(item.kind),
                size: AppSpacing.iconMedium,
                color: colors.primary,
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.title,
                      style: TextStyle(
                        color: colors.onSurface,
                        fontSize: AppTypography.body,
                        fontWeight: AppTypography.medium,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Wrap(
                      spacing: AppSpacing.intraGroupSm,
                      runSpacing: AppSpacing.intraGroupXs,
                      children: [
                        _MetadataLabel(text: tripItemKindLabel(item.kind)),
                        if (time.isNotEmpty) _MetadataLabel(text: time),
                        if (item.moments.isNotEmpty)
                          _MetadataLabel(
                            text:
                                '${item.moments.length}${TravelText.momentSuffix}',
                          ),
                        if (item.contentLinks.isNotEmpty)
                          _MetadataLabel(
                            text:
                                '${item.contentLinks.length}${TravelText.contentSuffix}',
                          ),
                      ],
                    ),
                    if ((item.note ?? '').trim().isNotEmpty) ...[
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        item.note!.trim(),
                        style: TextStyle(
                          color: colors.onSurfaceVariant,
                          fontSize: AppTypography.secondary,
                        ),
                      ),
                    ],
                    if (item.moments.isNotEmpty) ...[
                      SizedBox(height: AppSpacing.containerSm),
                      for (final moment in item.moments)
                        _MomentRow(
                          moment: moment,
                          onManage:
                              onManageMoment != null &&
                                  manageableMomentIds.contains(moment.momentId)
                              ? () => onManageMoment!(moment.momentId)
                              : null,
                        ),
                    ],
                    if (item.contentLinks.isNotEmpty) ...[
                      SizedBox(height: AppSpacing.intraGroupXs),
                      for (final link in item.contentLinks)
                        _ContentLinkRow(
                          link: link,
                          onOpen: onOpenPost == null
                              ? null
                              : () => onOpenPost!(link.postId),
                        ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

final class _MomentRow extends StatelessWidget {
  const _MomentRow({required this.moment, required this.onManage});

  final TripTimelineMomentSlice moment;
  final VoidCallback? onManage;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final inlineText = (moment.inlineText ?? '').trim();
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.intraGroupXs),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            tripMomentKindIcon(moment.kind),
            color: colors.secondary,
            size: AppSpacing.iconSmall,
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          Expanded(
            child: Text(
              inlineText.isNotEmpty
                  ? inlineText
                  : tripMomentKindLabel(moment.kind),
              style: TextStyle(
                color: colors.onSurfaceVariant,
                fontSize: AppTypography.secondary,
              ),
            ),
          ),
          if (onManage != null)
            IconButton(
              onPressed: onManage,
              tooltip: TravelText.manageMoment,
              icon: const Icon(CupertinoIcons.ellipsis),
              color: colors.onSurfaceVariant,
              iconSize: AppSpacing.iconSmall,
            ),
        ],
      ),
    );
  }
}

final class _ContentLinkRow extends StatelessWidget {
  const _ContentLinkRow({required this.link, required this.onOpen});

  final TripTimelineContentLinkSlice link;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: TextButton.icon(
        onPressed: onOpen,
        icon: const Icon(CupertinoIcons.doc_text),
        label: const Text(TravelText.openLinkedPost),
      ),
    );
  }
}

String tripMomentKindLabel(TripMomentKind kind) => switch (kind) {
  TripMomentKind.photo => TravelText.momentPhoto,
  TripMomentKind.video => TravelText.momentVideo,
  TripMomentKind.voice => TravelText.momentVoice,
  TripMomentKind.text => TravelText.momentTextTitle,
  TripMomentKind.checkIn => TravelText.momentCheckIn,
  TripMomentKind.postReference => TravelText.momentPostReference,
};

IconData tripMomentKindIcon(TripMomentKind kind) => switch (kind) {
  TripMomentKind.photo => CupertinoIcons.photo,
  TripMomentKind.video => CupertinoIcons.video_camera,
  TripMomentKind.voice => CupertinoIcons.mic,
  TripMomentKind.text => CupertinoIcons.text_quote,
  TripMomentKind.checkIn => CupertinoIcons.location,
  TripMomentKind.postReference => CupertinoIcons.doc_text,
};

final class _MetadataLabel extends StatelessWidget {
  const _MetadataLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: TextStyle(
        color: Theme.of(context).colorScheme.onSurfaceVariant,
        fontSize: AppTypography.secondary,
      ),
    );
  }
}

final class _CountBadge extends StatelessWidget {
  const _CountBadge({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.xs,
      ),
      decoration: BoxDecoration(
        color: colors.secondaryContainer,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: AppSpacing.iconSmall,
            color: colors.onSecondaryContainer,
          ),
          SizedBox(width: AppSpacing.xs),
          Text(
            label,
            style: TextStyle(
              color: colors.onSecondaryContainer,
              fontSize: AppTypography.caption,
            ),
          ),
        ],
      ),
    );
  }
}
