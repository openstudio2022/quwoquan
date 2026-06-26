part of 'image_editor_page.dart';

extension _ImageEditorPageProTools on _ImageEditorPageState {
  void _handleBack() {
    _onDone();
  }

  List<_ProToolboxEntry> _buildProToolboxEntries() {
    return <_ProToolboxEntry>[
      _ProToolboxEntry(
        icon: Icons.tune,
        label: UITextConstants.imageEditorProTabOverall,
        category: kImageEditorProCategoryOverall,
      ),
      _ProToolboxEntry(
        icon: Icons.place_outlined,
        label: UITextConstants.imageEditorProTabLocal,
        category: kImageEditorProCategoryLocal,
      ),
      _ProToolboxEntry(
        icon: Icons.circle_outlined,
        label: UITextConstants.imageEditorProHsl,
        category: kImageEditorProCategoryHsl,
        semanticIconKey: kEditorIconHslSolid,
      ),
      _ProToolboxEntry(
        icon: Icons.crop_16_9_outlined,
        label: UITextConstants.imageEditorProBwLevels,
        category: kImageEditorProCategoryBwLevels,
        semanticIconKey: kEditorIconBwLevels,
      ),
      _ProToolboxEntry(
        icon: Icons.show_chart,
        label: UITextConstants.imageEditorProCurve,
        category: kImageEditorProCategoryCurve,
      ),
      _ProToolboxEntry(
        icon: Icons.wb_sunny_outlined,
        label: UITextConstants.imageEditorProWhiteBalance,
        category: kImageEditorProCategoryWhiteBalance,
      ),
      _ProToolboxEntry(
        icon: Icons.crop_free,
        label: UITextConstants.imageEditorProPerspective,
        category: kImageEditorProCategoryPerspective,
      ),
      _ProToolboxEntry(
        icon: Icons.healing_outlined,
        label: UITextConstants.imageEditorProHeal,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProHeal,
      ),
      _ProToolboxEntry(
        icon: Icons.tonality_outlined,
        label: UITextConstants.imageEditorProToneContrast,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProToneContrast,
      ),
      _ProToolboxEntry(
        icon: Icons.auto_awesome_outlined,
        label: UITextConstants.imageEditorProGlamourGlow,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProGlamourGlow,
      ),
      _ProToolboxEntry(
        icon: Icons.shutter_speed_outlined,
        label: UITextConstants.imageEditorProSharpen,
        category: kImageEditorProCategoryPerspective,
        placeholderTitle: UITextConstants.imageEditorProSharpen,
      ),
    ];
  }

  void _openProEditorFromToolbox(_ProToolboxEntry entry) {
    _setEditorState(() {
      _showProToolbox = false;
      _selectedToolIndex = kImageEditorToolPro;
      _selectedProCategory = entry.category;
      _proPlaceholderTitle = entry.placeholderTitle;
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _localShowAnchorMenu = false;
      _localRangeVisible = false;
      _localAddMode = false;
      _isComparingSessionBaseline = false;
      if (entry.category == kImageEditorProCategoryHsl) {
        _resetHslSessionHistory();
      }
      if (entry.category == kImageEditorProCategoryBwLevels) {
        _resetBwSessionHistory();
      }
      if (entry.category == kImageEditorProCategoryOverall ||
          entry.category == kImageEditorProCategoryLocal) {
        _resetLocalSessionHistory();
      }
      _prepareProPanelSnapshot();
    });
  }

  Widget _buildProToolboxOverlay(double bottomPad) {
    final entries = _buildProToolboxEntries();
    final borderColor = AppColors.white.withValues(alpha: 0.10);
    final popupBottom = bottomPad + AppSpacing.bottomNavHeight + AppSpacing.sm;
    return Positioned.fill(
      child: Stack(
        children: [
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            bottom: popupBottom,
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => _setEditorState(() => _showProToolbox = false),
              child: const SizedBox.expand(),
            ),
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: popupBottom,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.black.withValues(alpha: 0.96),
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.largeBorderRadius),
                ),
                border: Border(
                  top: BorderSide(color: borderColor),
                  left: BorderSide(color: borderColor),
                  right: BorderSide(color: borderColor),
                ),
              ),
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.containerSm,
                  AppSpacing.intraGroupXs,
                  AppSpacing.containerSm,
                  AppSpacing.intraGroupXs,
                ),
                child: GridView.builder(
                  shrinkWrap: true,
                  itemCount: entries.length,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 5,
                    crossAxisSpacing: AppSpacing.intraGroupSm,
                    mainAxisSpacing: AppSpacing.intraGroupXs,
                    childAspectRatio: 1.02,
                  ),
                  itemBuilder: (context, index) {
                    final entry = entries[index];
                    final unselectedColor = AppColors.white.withValues(
                      alpha: 0.6,
                    );
                    return CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: () => _openProEditorFromToolbox(entry),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          if (entry.semanticIconKey != null)
                            ImageEditorSemanticIcon(
                              iconKey: entry.semanticIconKey!,
                              size: AppSpacing.iconLarge,
                              color: unselectedColor,
                            )
                          else
                            Icon(
                              entry.icon,
                              size: AppSpacing.iconLarge,
                              color: unselectedColor,
                            ),
                          SizedBox(
                            height: AppSpacing.toolPanelItemIconLabelGap,
                          ),
                          Text(
                            entry.label,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              fontSize: AppTypography.sm,
                              color: unselectedColor,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
