part of 'image_editor_operation_panel.dart';

/// 滤镜面板：分类 chips 条 + 模板横向列表（预览缩略图 + 名称色条）。
extension _ImageEditorOperationPanelFilter on ImageEditorOperationPanel {
  Widget _buildFilterCategoryBar() {
    if (filterCatalogLoading || filterCatalogLoadFailed) {
      return SizedBox(height: AppSpacing.subTabNavigationHeight);
    }
    return SizedBox(
      height: AppSpacing.subTabNavigationHeight,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerSm,
          vertical: AppSpacing.xs,
        ),
        children: [
          _buildFilterRemoveChip(),
          ...List.generate(filterCategories.length, (i) {
            return Padding(
              padding: EdgeInsets.only(left: AppSpacing.filterCategoryChipGap),
              child: _buildFilterCategoryChip(i),
            );
          }),
        ],
      ),
    );
  }

  Widget _buildFilterTemplateList() {
    if (filterCatalogLoading) {
      return SizedBox(
        key: const ValueKey<String>('image_editor_filter_catalog_loading'),
        height:
            AppSpacing.filterTemplatePreviewSize +
            AppSpacing.filterTemplateLabelBarHeight +
            AppSpacing.intraGroupSm,
        child: const Center(child: CupertinoActivityIndicator()),
      );
    }
    if (filterCatalogLoadFailed) {
      return SizedBox(
        key: const ValueKey<String>('image_editor_filter_catalog_failure'),
        height:
            AppSpacing.filterTemplatePreviewSize +
            AppSpacing.filterTemplateLabelBarHeight +
            AppSpacing.intraGroupSm,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                UITextConstants.imageEditorFilterLoadFailed,
                style: TextStyle(
                  color: foregroundSecondary,
                  fontSize: AppTypography.sm,
                ),
              ),
              CupertinoButton(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.xs,
                ),
                onPressed: onFilterCatalogRetry,
                child: const Text(UITextConstants.tryAgain),
              ),
            ],
          ),
        ),
      );
    }
    final itemWidth = AppSpacing.filterTemplateItemWidth;
    final itemExtent = AppSpacing.filterTemplateItemExtent;
    final previewSide = AppSpacing.filterTemplatePreviewSize;
    final labelBarHeight = AppSpacing.filterTemplateLabelBarHeight;
    final listVerticalPadding = AppSpacing.xs;
    final maxCardBorderInset = AppSpacing.toolPanelItemBorderWidthSelected * 2;
    final filterCardHeight = previewSide + labelBarHeight + maxCardBorderInset;
    final filterRowHeight =
        filterCardHeight + listVerticalPadding * 2 + AppSpacing.intraGroupXs;
    return LayoutBuilder(
      builder: (context, constraints) {
        final viewport = constraints.maxWidth;
        WidgetsBinding.instance.addPostFrameCallback((_) {
          _notifyFilterVisibleRange(viewport, itemExtent);
        });
        return SizedBox(
          height: filterRowHeight,
          child: NotificationListener<ScrollUpdateNotification>(
            onNotification: (_) {
              _notifyFilterVisibleRange(viewport, itemExtent);
              _syncFilterCategoryWithScroll(itemExtent);
              return false;
            },
            child: ListView.builder(
              controller: filterTemplateScrollController,
              scrollDirection: Axis.horizontal,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: listVerticalPadding,
              ),
              itemCount: filterPresets.length,
              itemBuilder: (context, i) {
                final preset = filterPresets[i];
                final selected = filterTemplateIndex == i;
                final isCategoryStart =
                    i > 0 && filterCategoryAnchors.contains(i);
                final borderWidth = selected
                    ? AppSpacing.toolPanelItemBorderWidthSelected
                    : AppSpacing.toolPanelItemBorderWidthUnselected;
                final preview = filterTemplatePreviewBytes[i];
                final loading = filterTemplatePreviewLoadingIndices.contains(i);
                final labelBarColor = _resolveFilterLabelBarColor(
                  preset,
                  selected: selected,
                );
                return Padding(
                  padding: EdgeInsets.only(
                    left: isCategoryStart
                        ? AppSpacing.filterTemplateCategoryGap
                        : 0,
                    right: AppSpacing.filterTemplateItemGap,
                  ),
                  child: SizedBox(
                    width: itemWidth,
                    child: GestureDetector(
                      onTap: () => onFilterTemplateChanged(i),
                      child: Container(
                        width: previewSide,
                        height: filterCardHeight,
                        decoration: BoxDecoration(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.smallBorderRadius,
                          ),
                          border: Border.all(
                            color: selected
                                ? foregroundColor
                                : foregroundSecondary.withValues(alpha: 0.30),
                            width: borderWidth,
                          ),
                          color: AppColors.white.withValues(alpha: 0.04),
                        ),
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(
                            AppSpacing.smallBorderRadius,
                          ),
                          child: Column(
                            mainAxisSize: MainAxisSize.max,
                            children: [
                              Expanded(
                                child: _buildFilterPreviewContent(
                                  preview: preview,
                                  loading: loading,
                                ),
                              ),
                              SizedBox(
                                width: double.infinity,
                                height: labelBarHeight,
                                child: Container(
                                  alignment: Alignment.center,
                                  color: labelBarColor,
                                  padding: EdgeInsets.symmetric(
                                    horizontal: AppSpacing.intraGroupXs,
                                  ),
                                  child: Text(
                                    preset.name,
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    textAlign: TextAlign.center,
                                    style: TextStyle(
                                      fontSize: AppTypography.xs,
                                      color: selected
                                          ? AppColors.white.withValues(
                                              alpha: 0.96,
                                            )
                                          : AppColors.white.withValues(
                                              alpha: 0.72,
                                            ),
                                      fontWeight: selected
                                          ? FontWeight.w600
                                          : FontWeight.w500,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }

  Widget _buildFilterRemoveChip() {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.subTabNavigationHeight),
      onPressed: onFilterRemove,
      child: Icon(
        CupertinoIcons.clear_circled,
        color: foregroundSecondary.withValues(alpha: 0.82),
        size: AppSpacing.iconMedium,
      ),
    );
  }

  Widget _buildFilterCategoryChip(int categoryIndex) {
    final selected = filterCategoryIndex == categoryIndex;
    final chip = _panelChip(
      filterCategories[categoryIndex].label,
      selected,
      onTap: () => _onTapFilterCategory(categoryIndex),
      fontSize: AppTypography.md,
    );
    if (!selected) return chip;
    return Builder(
      builder: (context) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (!context.mounted) return;
          Scrollable.ensureVisible(
            context,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
            alignment: 0.5,
          );
        });
        return chip;
      },
    );
  }

  void _onTapFilterCategory(int categoryIndex) {
    onFilterCategoryChanged(categoryIndex);
    if (!filterTemplateScrollController.hasClients ||
        categoryIndex < 0 ||
        categoryIndex >= filterCategoryAnchors.length) {
      return;
    }
    final itemExtent = AppSpacing.filterTemplateItemExtent;
    final targetIndex = filterCategoryAnchors[categoryIndex]
        .clamp(0, math.max(0, filterPresets.length - 1))
        .toInt();
    final target = _offsetForTemplateIndex(targetIndex, itemExtent);
    filterTemplateScrollController.animateTo(
      target.clamp(
        0.0,
        filterTemplateScrollController.position.maxScrollExtent,
      ),
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
    );
  }

  void _notifyFilterVisibleRange(double viewportWidth, double itemWidth) {
    if (itemWidth <= 0 || filterPresets.isEmpty) return;
    final offset = filterTemplateScrollController.hasClients
        ? filterTemplateScrollController.offset
        : 0.0;
    final start = _indexForOffset(offset, itemWidth);
    final visibleCount = (viewportWidth / itemWidth).ceil() + 1;
    final end = (start + visibleCount).clamp(0, filterPresets.length - 1);
    onFilterVisibleRangeChanged(start, end);
  }

  void _syncFilterCategoryWithScroll(double itemWidth) {
    if (!filterTemplateScrollController.hasClients ||
        filterCategoryAnchors.isEmpty ||
        filterPresets.isEmpty ||
        itemWidth <= 0) {
      return;
    }
    final index = _indexForOffset(
      filterTemplateScrollController.offset,
      itemWidth,
    );
    var category = 0;
    for (var i = 0; i < filterCategoryAnchors.length; i++) {
      final anchor = filterCategoryAnchors[i];
      if (index >= anchor) {
        category = i;
      } else {
        break;
      }
    }
    if (category != filterCategoryIndex) {
      onFilterCategoryChanged(category);
    }
  }

  double _offsetForTemplateIndex(int index, double itemWidth) {
    final safeIndex = index.clamp(0, math.max(0, filterPresets.length - 1));
    var extra = 0.0;
    for (final anchor in filterCategoryAnchors) {
      if (anchor > 0 && anchor < safeIndex + 1) {
        extra += AppSpacing.filterTemplateCategoryGap;
      }
    }
    return safeIndex * itemWidth + extra;
  }

  int _indexForOffset(double offset, double itemWidth) {
    if (filterPresets.isEmpty) return 0;
    var best = 0;
    for (var i = 0; i < filterPresets.length; i++) {
      final start = _offsetForTemplateIndex(i, itemWidth);
      final end = start + itemWidth;
      if (offset < end) {
        best = i;
        break;
      }
      best = i;
    }
    return best.clamp(0, filterPresets.length - 1);
  }

  Widget _buildFilterPreviewContent({
    required Uint8List? preview,
    required bool loading,
  }) {
    if (preview != null) {
      return Image.memory(
        preview,
        fit: BoxFit.cover,
        filterQuality: FilterQuality.low,
      );
    }
    if (loading) {
      return Center(
        child: SizedBox(
          width: AppSpacing.iconSmall,
          height: AppSpacing.iconSmall,
          child: CupertinoActivityIndicator(),
        ),
      );
    }
    return Center(
      child: Icon(
        Icons.image_outlined,
        size: AppSpacing.iconMedium,
        color: foregroundSecondary.withValues(alpha: 0.6),
      ),
    );
  }

  Color _resolveFilterLabelBarColor(
    ImageEditorFilterPreset preset, {
    required bool selected,
  }) {
    final params = preset.adjustments;
    final name = preset.name;
    final alpha = selected ? 0.88 : 0.72;
    final temperature = params.temperature.clamp(-100, 100);
    final tint = params.tint.clamp(-100, 100);
    final saturationValue = params.saturation.clamp(-100, 100);
    final brightness = params.brightness.clamp(-100, 100);
    final fade = params.fade.clamp(-100, 100);
    final contrast = params.contrast.clamp(-100, 100);
    final lightSense = params.lightSense.clamp(-100, 100);
    final highlight = params.highlight.clamp(-100, 100);
    final shadow = params.shadow.clamp(-100, 100);
    final calibrated = _filterPresetHslOverrides[preset.id];
    if (calibrated != null) {
      return HSLColor.fromAHSL(
        alpha,
        calibrated[0],
        calibrated[1],
        calibrated[2],
      ).toColor();
    }
    if (preset.categoryId == 'bw_art') {
      final bwLightness =
          (0.40 +
                  contrast / 320 +
                  brightness / 320 +
                  highlight / 420 +
                  shadow / 520)
              .clamp(0.28, 0.64);
      return HSLColor.fromAHSL(alpha, 0, 0, bwLightness).toColor();
    }
    final profile =
        _filterCategoryHslProfiles[preset.categoryId] ??
        const <double>[214, 0.54, 0.46];
    var hue = profile[0];
    var saturation = profile[1];
    var lightness = profile[2];
    // 参数驱动：温度偏暖 -> 偏橙；偏冷 -> 偏蓝（摄影常见色温方向）
    if (temperature > 0) {
      hue = _blendHue(hue, 34, (temperature / 100) * 0.55);
    } else if (temperature < 0) {
      hue = _blendHue(hue, 210, (-temperature / 100) * 0.55);
    }
    // 色调偏移：正向洋红，负向青绿
    if (tint > 0) {
      hue = _blendHue(hue, 326, (tint / 100) * 0.42);
    } else if (tint < 0) {
      hue = _blendHue(hue, 170, (-tint / 100) * 0.42);
    }
    // 名称语义覆盖：保证视觉与命名一致（奶油/冷霜/粉雾等）
    if (_containsAny(name, const ['奶油', '暖', '琥珀', '金', '日落'])) {
      hue = _blendHue(hue, 34, 0.70);
      saturation += 0.03;
      lightness += 0.04;
    } else if (_containsAny(name, const ['冷', '蓝', '海', '雪', '霜', '冰'])) {
      hue = _blendHue(hue, 208, 0.68);
      saturation += 0.02;
      lightness += 0.01;
    } else if (_containsAny(name, const ['粉', '樱', '柔', '梦'])) {
      hue = _blendHue(hue, 332, 0.62);
      saturation += 0.03;
      lightness += 0.03;
    } else if (_containsAny(name, const ['绿', '薄荷', '新芽'])) {
      hue = _blendHue(hue, 145, 0.62);
      saturation += 0.02;
    }
    // 摄影审校模式：禁用扰动，保证色块值稳定可复核
    saturation =
        (saturation +
                saturationValue / 220 +
                (contrast > 0 ? contrast / 520 : 0) -
                (fade > 0 ? fade / 620 : 0))
            .clamp(0.34, 0.76);
    lightness =
        (lightness +
                brightness / 240 +
                lightSense / 560 +
                highlight / 520 +
                shadow / 760 +
                fade / 280 -
                (contrast > 0 ? contrast / 560 : 0))
            .clamp(0.30, 0.66);
    return HSLColor.fromAHSL(alpha, hue, saturation, lightness).toColor();
  }

  static const Map<String, List<double>> _filterCategoryHslProfiles =
      <String, List<double>>{
        'texture': <double>[170, 0.48, 0.43],
        'portrait': <double>[336, 0.45, 0.53],
        'fresh_natural': <double>[138, 0.46, 0.50],
        'landscape_travel': <double>[196, 0.54, 0.48],
        'food': <double>[28, 0.60, 0.48],
        'film_retro': <double>[30, 0.42, 0.42],
        'movie_dream': <double>[290, 0.50, 0.50],
        'bw_art': <double>[0, 0.00, 0.44],
        'seasons': <double>[36, 0.58, 0.52],
      };
  // 摄影师视角精调：关键滤镜使用精准 HSL 标定，优先级最高
  static const Map<String, List<double>> _filterPresetHslOverrides =
      <String, List<double>>{
        'texture_clear': <double>[178, 0.40, 0.44],
        'texture_soft': <double>[26, 0.22, 0.60],
        'texture_depth': <double>[176, 0.34, 0.38],
        'beauty_softskin': <double>[20, 0.38, 0.62],
        'beauty_clean': <double>[28, 0.32, 0.60],
        'beauty_milky': <double>[38, 0.42, 0.64],
        'portrait_softlight': <double>[344, 0.42, 0.60],
        'portrait_cool': <double>[210, 0.42, 0.54],
        'portrait_movie': <double>[200, 0.34, 0.42],
        'blue_light': <double>[202, 0.66, 0.54],
        'blue_deep': <double>[210, 0.60, 0.36],
        'blue_ice': <double>[196, 0.52, 0.56],
        'food_fresh': <double>[24, 0.70, 0.52],
        'food_warm': <double>[30, 0.64, 0.50],
        'food_dessert': <double>[22, 0.68, 0.56],
        'retro_oldtime': <double>[30, 0.36, 0.42],
        'retro_hk': <double>[346, 0.42, 0.42],
        'retro_brown': <double>[26, 0.46, 0.38],
        'film_n': <double>[30, 0.34, 0.42],
        'film_warm': <double>[34, 0.42, 0.45],
        'film_green': <double>[146, 0.34, 0.40],
        'natural_origin': <double>[122, 0.32, 0.44],
        'natural_air': <double>[126, 0.28, 0.52],
        'natural_balance': <double>[124, 0.30, 0.46],
        'landscape_mountain': <double>[136, 0.48, 0.40],
        'landscape_coast': <double>[192, 0.54, 0.44],
        'landscape_sunset': <double>[26, 0.66, 0.50],
        'dream_haze': <double>[318, 0.34, 0.62],
        'dream_pink': <double>[334, 0.58, 0.62],
        'dream_focus': <double>[328, 0.42, 0.64],
        'oil_canvas': <double>[34, 0.50, 0.44],
        'oil_thick': <double>[30, 0.56, 0.40],
        'oil_vintage': <double>[34, 0.42, 0.48],
        'movie_teal_orange': <double>[188, 0.56, 0.40],
        'movie_lowsat': <double>[196, 0.22, 0.40],
        'movie_dark': <double>[224, 0.34, 0.32],
        'fresh_mint': <double>[146, 0.56, 0.52],
        'fresh_morning': <double>[148, 0.42, 0.54],
        'fresh_white': <double>[150, 0.30, 0.60],
        'bw_classic': <double>[0, 0.00, 0.42],
        'bw_silver': <double>[0, 0.00, 0.48],
        'bw_matte': <double>[0, 0.00, 0.40],
        'seasons_spring_blossom': <double>[334, 0.58, 0.62],
        'seasons_spring_green': <double>[94, 0.56, 0.52],
        'seasons_spring_sunny': <double>[46, 0.68, 0.56],
        'seasons_summer_breeze': <double>[202, 0.62, 0.50],
        'seasons_summer_soda': <double>[198, 0.62, 0.56],
        'seasons_summer_sun': <double>[190, 0.56, 0.50],
        'seasons_autumn_gold': <double>[34, 0.64, 0.52],
        'seasons_autumn_amber': <double>[24, 0.58, 0.46],
        'seasons_autumn_mist': <double>[30, 0.40, 0.50],
        'seasons_winter_frost': <double>[210, 0.52, 0.44],
        'seasons_winter_snow': <double>[202, 0.34, 0.60],
        'seasons_winter_morning': <double>[208, 0.44, 0.46],
      };

  bool _containsAny(String text, List<String> patterns) {
    for (final pattern in patterns) {
      if (text.contains(pattern)) return true;
    }
    return false;
  }

  double _normalizeHue(double hue) {
    var value = hue % 360;
    if (value < 0) value += 360;
    return value;
  }

  double _blendHue(double from, double to, double amount) {
    final a = _normalizeHue(from);
    final b = _normalizeHue(to);
    final t = amount.clamp(0.0, 1.0);
    var delta = b - a;
    if (delta.abs() > 180) {
      delta -= 360 * delta.sign;
    }
    return _normalizeHue(a + delta * t);
  }
}
