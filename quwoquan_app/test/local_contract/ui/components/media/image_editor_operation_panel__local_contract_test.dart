import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_operation_panel.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';

void main() {
  testWidgets('边框模板列表在图片编辑面板固定高度内不触发底部溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildPanelHarness(toolIndex: kImageEditorToolFrame),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
  });

  testWidgets('马赛克模板列表在图片编辑面板固定高度内不触发底部溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildPanelHarness(toolIndex: kImageEditorToolMosaic),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
  });
}

Widget _buildPanelHarness({required int toolIndex}) {
  final panelHeight = toolIndex == kImageEditorToolMosaic ? 300.0 : 210.0;
  return MaterialApp(
    home: Scaffold(
      backgroundColor: Colors.black,
      body: Align(
        alignment: Alignment.bottomCenter,
        child: SizedBox(
          height: panelHeight,
          width: double.infinity,
          child: ImageEditorOperationPanel(
            backgroundColor: Colors.black,
            foregroundColor: Colors.white,
            foregroundSecondary: Colors.white70,
            bottomInset: 0,
            toolIndex: toolIndex,
            selectedProToolIndex: null,
            selectedProCategory: kImageEditorProCategoryOverall,
            proPlaceholderTitle: null,
            proToolScrollController: ScrollController(),
            onSelectProTool: (_) {},
            onSelectProCategory: (_) {},
            onProToolScrollSync: (_, _) {},
            onExitProPanel: () {},
            onConfirmProPanel: () {},
            onCancelProTool: () {},
            onConfirmProTool: () {},
            onCancelPanel: () {},
            onConfirmPanel: () {},
            showCropReset: false,
            onCropReset: () {},
            cropRatio: 'original',
            onCropRatioChanged: (_) {},
            filterCategoryIndex: 0,
            filterTemplateIndex: 0,
            filterIntensity: 100,
            onFilterCategoryChanged: (_) {},
            onFilterTemplateChanged: (_) {},
            onFilterIntensityChanged: (_) {},
            filterCategories: const <ImageEditorFilterCategory>[],
            filterCategoryAnchors: const <int>[],
            filterPresets: const <ImageEditorFilterPreset>[],
            filterTemplatePreviewBytes: const <int, Uint8List>{},
            filterTemplatePreviewLoadingIndices: const <int>{},
            filterTemplateScrollController: ScrollController(),
            onFilterVisibleRangeChanged: (_, _) {},
            onFilterRemove: () {},
            mosaicTypeIndex: 0,
            mosaicBrushSize: 0.5,
            onMosaicTypeChanged: (_) {},
            onMosaicBrushSizeChanged: (_) {},
            frameTemplateIndex: 0,
            onFrameTemplateChanged: (_) {},
            textStyleIndex: 0,
            textColorIndex: 0,
            onTextStyleChanged: (_) {},
            onTextColorChanged: (_) {},
            rotateDegrees: 0,
            rotateFineDegrees: 0,
            flipHorizontal: false,
            flipVertical: false,
            onRotateLeft: () {},
            onRotateRight: () {},
            onRotateFineChanged: (_) {},
            onFlipHorizontal: () {},
            onFlipVertical: () {},
            showRotateReset: false,
            onRotateReset: () {},
            curveBrightness: 0,
            curveContrast: 0,
            whiteBalanceTemp: 0,
            onCurveBrightnessChanged: (_) {},
            onCurveContrastChanged: (_) {},
            onWhiteBalanceTempChanged: (_) {},
            bwWhiteLevel: 0,
            bwBlackLevel: 0,
            onBwWhiteLevelChanged: (_) {},
            onBwBlackLevelChanged: (_) {},
            proBaseSelectedIndex: 0,
            proBaseValues: const <String, double>{},
            onProBaseSelectedIndexChanged: (_) {},
            onProBaseValueChanged: (_, _) {},
            hslSelectedChannel: 'red',
            hslValues: const <String, Map<String, double>>{},
            hslPickerActive: false,
            onSelectHslChannel: (_) {},
            onHslValueChanged: (_, _) {},
            onToggleHslPicker: () {},
            localValues: const <String, double>{},
            hasSelectedLocalAnchor: false,
            localShowAllAnchors: false,
            localAddMode: false,
            onToggleLocalAddMode: () {},
            onToggleLocalShowAll: () {},
            localRangeVisible: false,
            onToggleLocalRangeVisible: () {},
            onCopyLocalAnchor: () {},
            onDeleteLocalAnchor: () {},
          ),
        ),
      ),
    ),
  );
}
