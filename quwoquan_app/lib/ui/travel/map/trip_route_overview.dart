import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/ui/travel/travel_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripRouteOverview extends StatelessWidget {
  const TripRouteOverview({super.key, required this.map, this.onOpenStop});

  final TripMapView map;
  final ValueChanged<TripMapStopSlice>? onOpenStop;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Semantics(
      container: true,
      label: TravelText.routeMap,
      child: DecoratedBox(
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
              Text(
                TravelText.routeMap,
                style: TextStyle(
                  color: colors.onSurface,
                  fontSize: AppTypography.sectionTitle,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
              SizedBox(height: AppSpacing.containerSm),
              if (map.stops.isEmpty)
                Text(
                  TravelText.noRouteStops,
                  style: TextStyle(
                    color: colors.onSurfaceVariant,
                    fontSize: AppTypography.body,
                  ),
                )
              else
                for (final stop in map.stops)
                  _RouteStop(stop: stop, onOpenStop: onOpenStop),
            ],
          ),
        ),
      ),
    );
  }
}

final class _RouteStop extends StatelessWidget {
  const _RouteStop({required this.stop, required this.onOpenStop});

  final TripMapStopSlice stop;
  final ValueChanged<TripMapStopSlice>? onOpenStop;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return InkWell(
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      onTap: onOpenStop == null ? null : () => onOpenStop!(stop),
      child: Padding(
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
                '${stop.sequence}',
                style: TextStyle(
                  color: colors.onPrimaryContainer,
                  fontSize: AppTypography.caption,
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    stop.title,
                    style: TextStyle(
                      color: colors.onSurface,
                      fontSize: AppTypography.body,
                      fontWeight: AppTypography.medium,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    '${TravelText.dayPrefix}${stop.dayIndex}${TravelText.daySuffix} · '
                    '${TravelText.stopPrefix}${stop.sequence}${TravelText.stopSuffix}',
                    style: TextStyle(
                      color: colors.onSurfaceVariant,
                      fontSize: AppTypography.secondary,
                    ),
                  ),
                ],
              ),
            ),
            if (onOpenStop != null)
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: colors.onSurfaceVariant,
              ),
          ],
        ),
      ),
    );
  }
}
