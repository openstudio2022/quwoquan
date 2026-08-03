part of 'assistant_presentation_renderer.dart';

class _AssistantRouteMapNode extends StatelessWidget {
  const _AssistantRouteMapNode({
    required this.node,
    required this.textColor,
    required this.colors,
    required this.toneColor,
    required this.compact,
  });

  final AssistantPresentationNodeWire node;
  final Color textColor;
  final AppColorsTheme colors;
  final Color toneColor;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final stops = _routeMapObjects(node.data['stops']);
    final segments = _routeMapObjects(node.data['segments']);
    final segmentByOrigin = <String, Map<String, dynamic>>{
      for (final segment in segments)
        _routeMapPlaceKey(segment['fromPlaceRef']): segment,
    };
    final orderedStops = [...stops]
      ..sort((left, right) {
        final day = (left['dayIndex'] as num).toInt().compareTo(
          (right['dayIndex'] as num).toInt(),
        );
        if (day != 0) return day;
        return (left['order'] as num).toInt().compareTo(
          (right['order'] as num).toInt(),
        );
      });
    final markerCounts = <String, int>{};
    for (final marker in _routeMapObjects(node.data['markers'])) {
      final key = _routeMapPlaceKey(marker['placeRef']);
      markerCounts[key] = (markerCounts[key] ?? 0) + 1;
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        if (node.title.isNotEmpty)
          Padding(
            padding: EdgeInsets.only(bottom: AppSpacing.intraGroupSm),
            child: SelectableText(
              node.title,
              style: TextStyle(
                color: textColor,
                fontSize: AppTypography.base,
                height: AppTypography.lineHeightRelaxed,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ),
        Container(
          width: double.infinity,
          padding: EdgeInsets.all(
            compact ? AppSpacing.containerXs : AppSpacing.containerSm,
          ),
          decoration: BoxDecoration(
            color: colors.backgroundSecondary,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: toneColor.withValues(alpha: 0.22)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final entry in orderedStops.indexed) ...[
                _stop(
                  entry.$1,
                  entry.$2,
                  markerCounts[_routeMapPlaceKey(entry.$2['placeRef'])] ?? 0,
                ),
                if (entry.$1 < orderedStops.length - 1)
                  _segment(
                    segmentByOrigin[_routeMapPlaceKey(entry.$2['placeRef'])],
                  ),
              ],
            ],
          ),
        ),
      ],
    );
  }

  Widget _stop(int index, Map<String, dynamic> stop, int markerCount) {
    final placeRef = (stop['placeRef'] as Map).cast<String, dynamic>();
    final title = (stop['title'] as String?)?.trim();
    final label = title?.isNotEmpty == true
        ? title!
        : (placeRef['objectId'] as String);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Container(
          width: AppSpacing.iconMedium,
          height: AppSpacing.iconMedium,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: toneColor.withValues(alpha: 0.12),
            shape: BoxShape.circle,
          ),
          child: Text(
            '${index + 1}',
            style: TextStyle(
              color: toneColor,
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: SelectableText(
            label,
            style: TextStyle(
              color: textColor,
              fontSize: AppTypography.base,
              height: AppTypography.lineHeightRelaxed,
            ),
          ),
        ),
        if (markerCount > 0) ...[
          SizedBox(width: AppSpacing.intraGroupSm),
          Icon(
            CupertinoIcons.photo,
            color: colors.foregroundSecondary,
            size: AppSpacing.iconSmall,
          ),
          SizedBox(width: AppSpacing.xs),
          Text(
            '$markerCount',
            style: TextStyle(
              color: colors.foregroundSecondary,
              fontSize: AppTypography.sm,
            ),
          ),
        ],
      ],
    );
  }

  Widget _segment(Map<String, dynamic>? segment) {
    final token = (segment?['modeToken'] as String?) ?? '';
    final icon = switch (token) {
      'walk' => CupertinoIcons.person,
      'bicycle' => Icons.directions_bike_outlined,
      'transit' || 'rail' => CupertinoIcons.tram_fill,
      'drive' => CupertinoIcons.car_detailed,
      'flight' => CupertinoIcons.airplane,
      'ferry' => Icons.directions_boat_outlined,
      _ => CupertinoIcons.arrow_down,
    };
    return SizedBox(
      height: AppSpacing.lg,
      child: Padding(
        padding: EdgeInsets.only(left: AppSpacing.intraGroupSm),
        child: Row(
          children: [
            Container(
              width: AppSpacing.hairline,
              height: AppSpacing.lg,
              color: toneColor.withValues(alpha: 0.34),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              icon,
              color: colors.foregroundSecondary,
              size: AppSpacing.iconSmall,
            ),
          ],
        ),
      ),
    );
  }
}
