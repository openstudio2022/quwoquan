part of 'image_editor_operation_panel.dart';

extension _ImageEditorOperationPanelPro on ImageEditorOperationPanel {
  Widget _buildEntryIcon(
    ImageEditorProToolEntry entry,
    Color color, {
    required double iconSize,
  }) {
    if (entry.semanticIconKey != null) {
      return ImageEditorSemanticIcon(
        iconKey: entry.semanticIconKey!,
        size: iconSize,
        color: color,
      );
    }
    return Icon(entry.icon, color: color, size: iconSize);
  }

  Widget _buildProToolsPanel(BuildContext context) {
    final isOverall = selectedProCategory == kImageEditorProCategoryOverall;
    final isLocal = selectedProCategory == kImageEditorProCategoryLocal;
    final isHsl = selectedProCategory == kImageEditorProCategoryHsl;
    final isBwLevels = selectedProCategory == kImageEditorProCategoryBwLevels;
    final isCurve = selectedProCategory == kImageEditorProCategoryCurve;
    final isWhiteBalance =
        selectedProCategory == kImageEditorProCategoryWhiteBalance;
    if (isOverall || isLocal) {
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildProAdjustPanelContent(context, showLocalControls: isLocal),
          _buildProPanelExitBar(),
        ],
      );
    }
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        isHsl
            ? _buildProHslPanelContent()
            : isBwLevels
            ? _buildProBwLevelsPanelContent()
            : isCurve
            ? ImageEditorCurvePanel(
                curves: curvesState,
                channel: curveChannel,
                histogram: curveHistogram,
                onChannelChanged: onCurveChannelChanged,
                onCurvesChanged: onCurvesChanged,
                onResetChannel: onCurveResetChannel,
              )
            : isWhiteBalance
            ? _buildWhiteBalancePanelContent()
            : const SizedBox.shrink(),
        _buildProPanelExitBar(),
      ],
    );
  }

  Widget _buildWhiteBalancePanelContent() {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        children: [
          SizedBox(height: AppSpacing.sm),
          _buildHslAxisRow(
            UITextConstants.imageEditorProColorTemp,
            wbTemperature,
            gradient: const <Color>[
              AppColors.info,
              AppColors.white,
              AppColors.warning,
            ],
            onChanged: onWbTemperatureChanged,
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProTone,
            wbTint,
            gradient: const <Color>[
              AppColors.success,
              AppColors.white,
              AppColors.secondaryColor,
            ],
            onChanged: onWbTintChanged,
          ),
          CupertinoButton(
            onPressed: onWbAuto,
            child: Text(UITextConstants.imageEditorProWhiteBalanceAuto),
          ),
        ],
      ),
    );
  }

  Widget _buildProBwLevelsPanelContent() {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        children: [
          SizedBox(height: AppSpacing.sm),
          _buildHslAxisRow(
            UITextConstants.imageEditorProWhiteLevel,
            bwWhiteLevel,
            gradient: <Color>[
              AppColors.white.withValues(alpha: 0.08),
              AppColors.white.withValues(alpha: 0.95),
            ],
            onChanged: onBwWhiteLevelChanged,
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProBlackLevel,
            bwBlackLevel,
            gradient: <Color>[
              AppColors.white.withValues(alpha: 0.95),
              AppColors.white.withValues(alpha: 0.12),
            ],
            onChanged: onBwBlackLevelChanged,
          ),
          SizedBox(height: AppSpacing.xs),
        ],
      ),
    );
  }

  Widget _buildProAdjustPanelContent(
    BuildContext context, {
    required bool showLocalControls,
  }) {
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (showLocalControls) _buildLocalControlButtonsRow(),
          if (showLocalControls) SizedBox(height: AppSpacing.xs / 2),
          SizedBox(
            height: AppSpacing.bottomNavHeight + AppSpacing.sm * 2,
            child: _buildProBasePanelContent(context),
          ),
        ],
      ),
    );
  }

  Widget _buildLocalControlButtonsRow() {
    final items = <_LocalControlButtonItem>[
      _LocalControlButtonItem(
        icon: Icons.add_circle_outline,
        selected: localAddMode,
        label: UITextConstants.imageEditorProAnchorAdd,
        onTap: onToggleLocalAddMode,
      ),
      _LocalControlButtonItem(
        icon: localShowAllAnchors
            ? Icons.visibility_outlined
            : Icons.visibility,
        selected: !localShowAllAnchors,
        label: localShowAllAnchors
            ? UITextConstants.imageEditorProAnchorHide
            : UITextConstants.imageEditorProAnchorShow,
        onTap: onToggleLocalShowAll,
      ),
      _LocalControlButtonItem(
        icon: localRangeVisible ? Icons.radar : Icons.radar_outlined,
        selected: localRangeVisible,
        label: localRangeVisible
            ? UITextConstants.imageEditorProAnchorRangeHide
            : UITextConstants.imageEditorProAnchorRangeShow,
        onTap: onToggleLocalRangeVisible,
      ),
    ];
    return SizedBox(
      height: AppSpacing.bottomNavHeight,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
        children: items
            .asMap()
            .entries
            .map((entry) {
              final index = entry.key;
              final item = entry.value;
              final color = item.selected
                  ? (index == 0 ? AppColors.primaryColor : foregroundColor)
                  : foregroundSecondary.withValues(alpha: 0.8);
              return CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.xs,
                ),
                minimumSize: Size.zero,
                onPressed: item.onTap,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      item.icon,
                      color: color,
                      size: AppSpacing.toolPanelItemIconSize,
                    ),
                    SizedBox(width: AppSpacing.toolPanelItemIconLabelGap),
                    Text(
                      item.label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        color: color,
                        fontSize: AppTypography.toolPanelItemLabel,
                        fontWeight: FontWeight.normal,
                      ),
                    ),
                  ],
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }

  Widget _buildProHslPanelContent() {
    final channelValues =
        hslValues[hslSelectedChannel] ?? const <String, double>{};
    final hue = channelValues[kHslAxisHue] ?? 0;
    final saturation = channelValues[kHslAxisSaturation] ?? 0;
    final luminance = channelValues[kHslAxisLuminance] ?? 0;
    final selectedChannel = kImageEditorHslChannels.firstWhere(
      (channel) => channel.key == hslSelectedChannel,
      orElse: () => kImageEditorHslChannels.first,
    );
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
      child: Column(
        children: [
          SizedBox(height: AppSpacing.xs),
          SizedBox(
            height: AppSpacing.bottomNavHeight,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: kImageEditorHslChannels.length,
              separatorBuilder: (context, index) =>
                  SizedBox(width: AppSpacing.intraGroupSm),
              itemBuilder: (context, index) =>
                  _buildHslChannelItem(kImageEditorHslChannels[index]),
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          _buildHslAxisRow(
            UITextConstants.imageEditorProHue,
            hue,
            gradient: _buildHslAxisGradient(selectedChannel.color, kHslAxisHue),
            onChanged: (v) => onHslValueChanged(kHslAxisHue, v),
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProSaturation,
            saturation,
            gradient: _buildHslAxisGradient(
              selectedChannel.color,
              kHslAxisSaturation,
            ),
            onChanged: (v) => onHslValueChanged(kHslAxisSaturation, v),
          ),
          SizedBox(height: AppSpacing.xs),
          _buildHslAxisRow(
            UITextConstants.imageEditorProLuminance,
            luminance,
            gradient: _buildHslAxisGradient(
              selectedChannel.color,
              kHslAxisLuminance,
            ),
            onChanged: (v) => onHslValueChanged(kHslAxisLuminance, v),
          ),
          SizedBox(height: AppSpacing.xs),
        ],
      ),
    );
  }

  Widget _buildHslChannelItem(ImageEditorHslChannel channel) {
    final selected = hslSelectedChannel == channel.key;
    return GestureDetector(
      onTap: () => onSelectHslChannel(channel.key),
      child: SizedBox(
        width: AppSpacing.bottomNavHeight - AppSpacing.xs,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: AppSpacing.iconLarge,
              height: AppSpacing.iconLarge,
              margin: EdgeInsets.only(top: AppSpacing.xs),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: channel.color,
                border: Border.all(
                  color: selected
                      ? AppColors.white
                      : AppColors.white.withValues(alpha: 0.35),
                  width: selected ? AppSpacing.xs / 2 : AppSpacing.xs / 4,
                ),
              ),
              child: selected
                  ? Center(
                      child: Container(
                        width: AppSpacing.iconLarge / 2,
                        height: AppSpacing.iconLarge / 2,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: AppColors.black.withValues(alpha: 0.7),
                            width: AppSpacing.xs / 3,
                          ),
                        ),
                      ),
                    )
                  : null,
            ),
            SizedBox(height: AppSpacing.xs / 2),
            Text(
              channel.label,
              style: TextStyle(
                color: selected
                    ? foregroundColor
                    : foregroundSecondary.withValues(alpha: 0.75),
                fontSize: AppTypography.sm,
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<Color> _buildHslAxisGradient(Color selectedColor, String axis) {
    final hsv = HSVColor.fromColor(selectedColor);
    if (axis == kHslAxisHue) {
      return <Color>[
        hsv
            .withHue((hsv.hue - 60 + 360) % 360)
            .withSaturation(1)
            .withValue(1)
            .toColor(),
        hsv.withSaturation(1).withValue(1).toColor(),
        hsv
            .withHue((hsv.hue + 60) % 360)
            .withSaturation(1)
            .withValue(1)
            .toColor(),
      ];
    }
    if (axis == kHslAxisSaturation) {
      return <Color>[
        HSLColor.fromColor(selectedColor).withSaturation(0).toColor(),
        HSLColor.fromColor(selectedColor).withSaturation(0.5).toColor(),
        HSLColor.fromColor(selectedColor).withSaturation(1).toColor(),
      ];
    }
    return <Color>[
      AppColors.black,
      HSLColor.fromColor(selectedColor).withLightness(0.5).toColor(),
      AppColors.white,
    ];
  }

  Widget _buildHslAxisRow(
    String label,
    double value, {
    required List<Color> gradient,
    required ValueChanged<double> onChanged,
  }) {
    return Row(
      children: [
        SizedBox(
          width: AppSpacing.bottomNavHeight,
          child: Text(
            label,
            style: TextStyle(
              color: foregroundColor,
              fontSize: AppTypography.sm,
            ),
          ),
        ),
        Expanded(
          child: _ProAdjustmentLine(
            value: value,
            min: -100,
            max: 100,
            trackHeight: AppSpacing.xs,
            trackGradient: LinearGradient(colors: gradient),
            onChanged: onChanged,
          ),
        ),
        SizedBox(width: AppSpacing.sm),
        SizedBox(
          width: AppSpacing.bottomNavHeight,
          child: Text(
            value.round().toString(),
            textAlign: TextAlign.right,
            style: TextStyle(
              color: foregroundColor,
              fontSize: AppTypography.sm,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildProBasePanelContent(BuildContext context) {
    final gap = AppSpacing.intraGroupSm;
    final itemWidth = AppSpacing.buttonHeight * 1.4;
    final itemIconSize = AppTypography.responsive(
      context,
      compact: AppSpacing.iconSmall,
      regular: AppSpacing.toolPanelItemIconSize,
      expanded: AppSpacing.toolPanelItemIconSize,
    );
    final itemLabelFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.toolPanelItemLabel,
      expanded: AppTypography.toolPanelItemLabel,
    );
    final itemLabelLineHeight = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppSpacing.toolPanelItemLabelLineHeight,
      expanded: AppSpacing.toolPanelItemLabelLineHeight,
    );
    final itemIconLabelGap = AppTypography.responsive(
      context,
      compact: AppSpacing.intraGroupXs,
      regular: AppSpacing.toolPanelItemIconLabelGap,
      expanded: AppSpacing.toolPanelItemIconLabelGap,
    );
    return SizedBox(
      height: AppSpacing.bottomNavHeight + AppSpacing.sm * 2,
      child: ListView.separated(
        controller: proToolScrollController,
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
        itemCount: kImageEditorProBaseEntries.length,
        separatorBuilder: (context, index) => SizedBox(width: gap),
        itemBuilder: (context, index) {
          final entry = kImageEditorProBaseEntries[index];
          final selected = proBaseSelectedIndex == index;
          final value = (proBaseValues[entry.type] ?? 0).round();
          return SizedBox(
            width: itemWidth,
            child: GestureDetector(
              onTap: () => onProBaseSelectedIndexChanged(index),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildEntryIcon(
                    entry,
                    selected
                        ? foregroundColor
                        : foregroundSecondary.withValues(alpha: 0.75),
                    iconSize: itemIconSize,
                  ),
                  SizedBox(height: itemIconLabelGap),
                  Text(
                    entry.label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: selected
                          ? foregroundColor
                          : foregroundSecondary.withValues(alpha: 0.75),
                      fontSize: itemLabelFontSize,
                      height: itemLabelLineHeight / itemLabelFontSize,
                      fontWeight: selected
                          ? FontWeight.w600
                          : FontWeight.normal,
                    ),
                  ),
                  SizedBox(height: itemIconLabelGap),
                  Text(
                    value.toString(),
                    style: TextStyle(
                      color: selected
                          ? foregroundColor
                          : foregroundSecondary.withValues(alpha: 0.75),
                      fontSize: itemLabelFontSize,
                      height: itemLabelLineHeight / itemLabelFontSize,
                      fontWeight: FontWeight.w600,
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

  Widget _buildProPanelExitBar() {
    final isAdjustPanel =
        selectedProCategory == kImageEditorProCategoryOverall ||
        selectedProCategory == kImageEditorProCategoryLocal;
    final centerTitle = selectedProCategory == kImageEditorProCategoryHsl
        ? UITextConstants.imageEditorProTabHsl
        : selectedProCategory == kImageEditorProCategoryBwLevels
        ? UITextConstants.imageEditorProTabBwLevels
        : selectedProCategory == kImageEditorProCategoryLocal
        ? UITextConstants.imageEditorProTabLocal
        : selectedProCategory == kImageEditorProCategoryCurve
        ? UITextConstants.imageEditorProCurve
        : selectedProCategory == kImageEditorProCategoryWhiteBalance
        ? UITextConstants.imageEditorProWhiteBalance
        : UITextConstants.imageEditorProAdjustImage;
    final safeIndex = proBaseSelectedIndex.clamp(
      0,
      kImageEditorProBaseEntries.length - 1,
    );
    final selectedEntry = kImageEditorProBaseEntries[safeIndex];
    final currentValue =
        selectedProCategory == kImageEditorProCategoryLocal &&
            hasSelectedLocalAnchor
        ? (localValues[selectedEntry.type] ?? 0)
        : (proBaseValues[selectedEntry.type] ?? 0);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
            onPressed: onExitProPanel,
            child: Icon(
              CupertinoIcons.xmark,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
            ),
          ),
          if (isAdjustPanel)
            Expanded(
              child: Padding(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                ),
                child: _ProAdjustmentLine(
                  value: currentValue,
                  min: -100,
                  max: 100,
                  onChanged: (v) =>
                      onProBaseValueChanged(selectedEntry.type, v),
                ),
              ),
            )
          else
            Expanded(
              child: Center(
                child: Text(
                  centerTitle,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.92),
                    fontSize: AppTypography.md,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.square(AppSpacing.iconButtonMinSizeMd),
            onPressed: onConfirmProPanel,
            child: Icon(
              CupertinoIcons.checkmark,
              color: AppColors.white,
              size: AppSpacing.iconLarge,
            ),
          ),
        ],
      ),
    );
  }
}
