import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripShareSnapshotView extends StatelessWidget {
  const TripShareSnapshotView({super.key, required this.snapshot});

  final TripShareSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final days = snapshot.items.map((item) => item.dayIndex).toSet().toList()
      ..sort();
    return SingleChildScrollView(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(
                CupertinoIcons.shield_lefthalf_fill,
                color: colors.primary,
                size: AppSpacing.iconMedium,
              ),
              SizedBox(width: AppSpacing.containerSm),
              Expanded(
                child: Text(
                  TravelText.sharePrivacySafe,
                  style: TextStyle(
                    color: colors.onSurfaceVariant,
                    fontSize: AppTypography.secondary,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.containerMd),
          Wrap(
            spacing: AppSpacing.containerSm,
            runSpacing: AppSpacing.containerSm,
            children: [
              _ShareMetric(
                label: TravelText.shareItems,
                value: snapshot.items.length,
              ),
              _ShareMetric(
                label: TravelText.moments,
                value: snapshot.moments.length,
              ),
              _ShareMetric(
                label: TravelText.linkedPosts,
                value: snapshot.contentLinks.length,
              ),
              _ShareMetric(
                label: TravelText.shareRouteStops,
                value: snapshot.routeStops.length,
              ),
            ],
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          for (final dayIndex in days) ...[
            Text(
              '${TravelText.dayPrefix}$dayIndex${TravelText.daySuffix}',
              style: TextStyle(
                color: colors.onSurface,
                fontSize: AppTypography.sectionTitle,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            for (final item in snapshot.items.where(
              (item) => item.dayIndex == dayIndex,
            ))
              _ShareItem(item: item),
            SizedBox(height: AppSpacing.interGroupMd),
          ],
        ],
      ),
    );
  }
}

final class _ShareMetric extends StatelessWidget {
  const _ShareMetric({required this.label, required this.value});

  final String label;
  final int value;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Chip(
      avatar: Text('$value'),
      label: Text(label),
      backgroundColor: colors.surfaceContainerHighest,
      side: BorderSide.none,
    );
  }
}

final class _ShareItem extends StatelessWidget {
  const _ShareItem({required this.item});

  final TripShareItemSlice item;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final title = (item.title ?? '').trim();
    return Padding(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
      child: Row(
        children: [
          Container(
            width: AppSpacing.iconLarge,
            height: AppSpacing.iconLarge,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: colors.primaryContainer,
              shape: BoxShape.circle,
            ),
            child: Text(
              '${item.orderInDay}',
              style: TextStyle(
                color: colors.onPrimaryContainer,
                fontSize: AppTypography.caption,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.containerSm),
          Expanded(
            child: Text(
              title.isEmpty ? item.kind : title,
              style: TextStyle(
                color: colors.onSurface,
                fontSize: AppTypography.body,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
