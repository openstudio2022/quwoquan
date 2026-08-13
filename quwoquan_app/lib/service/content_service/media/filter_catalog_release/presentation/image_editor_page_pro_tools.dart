part of 'image_editor_page.dart';

extension _ImageEditorPageProTools on _ImageEditorPageState {
  void _openProEditorFromToolbox(ImageEditorProToolEntry entry) {
    _setEditorState(() {
      _showProToolbox = false;
      _selectedToolIndex = kImageEditorToolPro;
      _selectedProCategory = entry.categoryIndex;
      _hslPickerActive = false;
      _hslPickerPoint = null;
      _localShowAnchorMenu = false;
      _localRangeVisible = false;
      _localAddMode = false;
      _isComparingSessionBaseline = false;
      if (entry.categoryIndex == kImageEditorProCategoryHsl) {
        _resetHslSessionHistory();
        _prepareHslPreviewSession();
      }
      if (entry.categoryIndex == kImageEditorProCategoryBwLevels) {
        _resetBwSessionHistory();
      }
      if (entry.categoryIndex == kImageEditorProCategoryOverall ||
          entry.categoryIndex == kImageEditorProCategoryLocal) {
        _resetLocalSessionHistory();
      }
      if (entry.categoryIndex == kImageEditorProCategoryOverall) {
        _prepareBasePreviewSession();
      }
      if (entry.categoryIndex == kImageEditorProCategoryLocal) {
        _prepareLocalPreviewSession();
      }
      if (entry.categoryIndex == kImageEditorProCategoryCurve) {
        _prepareCurveSession();
      }
      _prepareProPanelSnapshot();
    });
  }

  Widget _buildProToolboxOverlay(double bottomPad) {
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
                  itemCount: kImageEditorProCategoryEntries.length,
                  physics: const NeverScrollableScrollPhysics(),
                  gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 5,
                    crossAxisSpacing: AppSpacing.intraGroupSm,
                    mainAxisSpacing: AppSpacing.intraGroupXs,
                    childAspectRatio: 1.02,
                  ),
                  itemBuilder: (context, index) {
                    final entry = kImageEditorProCategoryEntries[index];
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
