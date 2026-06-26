part of 'image_editor_page.dart';

extension _ImageEditorPageHistoryLogic on _ImageEditorPageState {
  void _pushStep(ImageEditorStep step) {
    _setEditorState(() => _steps.add(step));
  }

  void _removeStepAt(int index) {
    if (index < 0 || index >= _steps.length) return;
    _setEditorState(() {
      _steps.removeAt(index);
      // 重算：当前为占位，实际应用时按顺序重算其后步骤并更新画布
    });
  }

  void _redoStepAt(int index) {
    if (index < 0 || index >= _steps.length) return;
    final step = _steps[index];
    _setEditorState(() {
      if (step.type == 'proTools') {
        final sub = step.params['subType'] as String?;
        if (sub == 'baseAdjustments') {
          final values =
              (step.params['values'] as Map?)?.map(
                (key, value) =>
                    MapEntry(key.toString(), (value as num?)?.toDouble() ?? 0),
              ) ??
              const <String, double>{};
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryOverall;
          _selectedProBaseToolIndex =
              (step.params['selectedIndex'] as int?) ??
              _selectedProBaseToolIndex;
          _proBaseValues
            ..clear()
            ..addAll({
              for (final entry in kImageEditorProBaseEntries)
                entry.type: values[entry.type] ?? 0,
            });
          _prepareProPanelSnapshot();
          return;
        }
        if (sub == 'hslAdjustments') {
          final valuesRaw =
              (step.params['values'] as Map?)?.map(
                (key, value) => MapEntry(key.toString(), value),
              ) ??
              const <String, Object?>{};
          final restored = createDefaultHslValues();
          for (final channel in kImageEditorHslChannels) {
            final channelMap = valuesRaw[channel.key];
            if (channelMap is Map) {
              restored[channel.key] = {
                kHslAxisHue: (channelMap[kHslAxisHue] as num?)?.toDouble() ?? 0,
                kHslAxisSaturation:
                    (channelMap[kHslAxisSaturation] as num?)?.toDouble() ?? 0,
                kHslAxisLuminance:
                    (channelMap[kHslAxisLuminance] as num?)?.toDouble() ?? 0,
              };
            }
          }
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryHsl;
          _selectedHslChannel =
              (step.params['selectedChannel'] as String?) ??
              kImageEditorHslChannels.first.key;
          _proHslValues = restored;
          _prepareProPanelSnapshot();
          return;
        }
        if (sub == 'bwLevelsAdjustments') {
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryBwLevels;
          _bwWhiteLevel =
              (step.params['whiteLevel'] as num?)?.toDouble() ?? _bwWhiteLevel;
          _bwBlackLevel =
              (step.params['blackLevel'] as num?)?.toDouble() ?? _bwBlackLevel;
          _prepareProPanelSnapshot();
          return;
        }
        if (sub == 'localAdjustments') {
          final restored = imageEditorParseLocalAnchorsFromParams(
            step.params,
            allocateId: () => _localAnchorIdSeed += 1,
          );
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProCategory = kImageEditorProCategoryLocal;
          _localAnchors
            ..clear()
            ..addAll(restored);
          if (restored.isNotEmpty) {
            _localAnchorIdSeed = restored
                .map((anchor) => anchor.id)
                .reduce(math.max);
          }
          _selectedLocalAnchorId =
              (step.params['selectedAnchorId'] as num?)?.toInt() ??
              (restored.isNotEmpty ? restored.last.id : null);
          _prepareProPanelSnapshot();
          return;
        }
        final i = kImageEditorProToolEntries.indexWhere(
          (entry) => entry.type == sub,
        );
        if (i >= 0) {
          _selectedToolIndex = kImageEditorToolPro;
          _selectedProToolIndex = i;
          _selectedProCategory = kImageEditorProToolEntries[i].categoryIndex;
          _curveBrightness =
              (step.params['curveBrightness'] as num?)?.toDouble() ??
              _curveBrightness;
          _curveContrast =
              (step.params['curveContrast'] as num?)?.toDouble() ??
              _curveContrast;
          _whiteBalanceTemp =
              (step.params['whiteBalanceTemp'] as num?)?.toDouble() ??
              _whiteBalanceTemp;
        }
      } else {
        if (step.type == 'filter') {
          final presetId = step.params['presetId'] as String?;
          final intensity =
              (step.params['intensity'] as num?)?.toDouble() ?? 100;
          _selectedFilterPresetId = presetId;
          _filterIntensity = intensity.clamp(0, 100);
          if (presetId != null && presetId.isNotEmpty) {
            _filterStrengthByPresetId[presetId] = _filterIntensity;
            final index = _filterPresets.indexWhere(
              (entry) => entry.id == presetId,
            );
            _filterTemplateIndex = index >= 0 ? index : -1;
            if (index >= 0) {
              _syncFilterCategoryFromTemplateIndex(index);
            }
          }
        }
        _selectedToolIndex = _toolIndexForType(step.type);
      }
    });
  }

  int _toolIndexForType(String type) {
    final i = kImageEditorToolTypes.indexOf(type);
    return i >= 0 ? i : kImageEditorToolCrop;
  }
}
