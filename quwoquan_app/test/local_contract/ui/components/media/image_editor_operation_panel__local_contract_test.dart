import 'dart:typed_data';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/editor/filter/image_editor_filter_models.dart';
import 'package:quwoquan_app/components/media/image/editor/models/image_editor_step_payload.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/curves/image_editor_curve_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/curves/image_editor_curve_panel.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/image_editor_operation_panel.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/mosaic/image_editor_mosaic_models.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/text/image_editor_text_models.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_pro_tool_entries.dart';
import 'package:quwoquan_app/components/media/image/editor/tool_list/image_editor_tool_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

void main() {
  test('图片编辑语义文案可从 UITextConstants 门面直接访问', () {
    const labels = <String>[
      UITextConstants.imageEditorProCurve,
      UITextConstants.imageEditorProCurveChannelRgb,
      UITextConstants.imageEditorProWhiteBalance,
      UITextConstants.imageEditorProWhiteBalanceAuto,
      UITextConstants.imageEditorTextStylePlain,
      UITextConstants.imageEditorTextStyleOutline,
      UITextConstants.imageEditorTextStyleBar,
      UITextConstants.imageEditorMosaicPixel,
      UITextConstants.imageEditorMosaicBlur,
    ];

    expect(labels, everyElement(isNotEmpty));
  });

  test('一级与专业工具只消费当前规范的有序定义', () {
    expect(kImageEditorToolEntries.map((entry) => entry.type), <String>[
      'filter',
      'crop',
      'rotate',
      'proTools',
      'text',
      'mosaic',
    ]);
    expect(
      kImageEditorProCategoryEntries.map((entry) => entry.categoryIndex),
      <int>[
        kImageEditorProCategoryOverall,
        kImageEditorProCategoryLocal,
        kImageEditorProCategoryHsl,
        kImageEditorProCategoryBwLevels,
        kImageEditorProCategoryCurve,
        kImageEditorProCategoryWhiteBalance,
      ],
    );
    expect(
      const ImageEditorCropStepPayload(ratio: 'original').label,
      imageEditorToolEntryAt(kImageEditorToolCrop).label,
    );
    expect(
      ImageEditorProCurvesStepPayload(curves: ImageEditorCurvesState()).label,
      imageEditorProCategoryEntryForType('curves')!.label,
    );
  });

  testWidgets('马赛克工具在图片编辑面板固定高度内不触发底部溢出', (tester) async {
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildPanelHarness(toolIndex: kImageEditorToolMosaic),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
  });

  testWidgets('曲线面板消费四通道状态并回传通道选择', (tester) async {
    ImageEditorCurveChannel? selectedChannel;
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildPanelHarness(
        toolIndex: kImageEditorToolPro,
        selectedProCategory: kImageEditorProCategoryCurve,
        onCurveChannelChanged: (channel) => selectedChannel = channel,
      ),
    );
    await tester.pump();

    expect(find.byType(ImageEditorCurvePanel), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorProCurveChannelRgb), findsOne);
    await tester.tap(find.text(UITextConstants.imageEditorProChannelRed));
    expect(selectedChannel, ImageEditorCurveChannel.red);
    expect(tester.takeException(), isNull);
  });

  testWidgets('白平衡面板展示色温色调并触发自动校正', (tester) async {
    var autoInvocations = 0;
    await tester.binding.setSurfaceSize(const Size(390, 844));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildPanelHarness(
        toolIndex: kImageEditorToolPro,
        selectedProCategory: kImageEditorProCategoryWhiteBalance,
        onWbAuto: () => autoInvocations++,
      ),
    );
    await tester.pump();

    expect(find.text(UITextConstants.imageEditorProColorTemp), findsOneWidget);
    expect(find.text(UITextConstants.imageEditorProTone), findsOneWidget);
    await tester.tap(find.text(UITextConstants.imageEditorProWhiteBalanceAuto));
    expect(autoInvocations, 1);
    expect(tester.takeException(), isNull);
  });

  testWidgets('文字面板使用强类型样式并回传选中项操作', (tester) async {
    ImageEditorTextStyleKind? selectedStyle;
    var deleteInvocations = 0;
    const item = ImageEditorTextItem(
      id: 1,
      text: '测试',
      style: ImageEditorTextStyleKind.plain,
      colorIndex: 0,
      center: Offset(0.5, 0.5),
      fontSizeOnShortSide: ImageEditorTextItem.defaultFontSizeOnShortSide,
      rotation: 0,
    );

    await tester.pumpWidget(
      _buildPanelHarness(
        toolIndex: kImageEditorToolText,
        selectedTextItem: item,
        onTextStyleChanged: (style) => selectedStyle = style,
        onTextDelete: () => deleteInvocations++,
      ),
    );
    await tester.pump();

    await tester.tap(find.text(UITextConstants.imageEditorTextStyleOutline));
    expect(selectedStyle, ImageEditorTextStyleKind.outline);
    await tester.tap(find.byIcon(CupertinoIcons.trash));
    expect(deleteInvocations, 1);
    expect(tester.takeException(), isNull);
  });
}

Widget _buildPanelHarness({
  required int toolIndex,
  int selectedProCategory = kImageEditorProCategoryOverall,
  ImageEditorTextItem? selectedTextItem,
  ValueChanged<ImageEditorTextStyleKind>? onTextStyleChanged,
  VoidCallback? onTextDelete,
  ValueChanged<ImageEditorCurveChannel>? onCurveChannelChanged,
  VoidCallback? onWbAuto,
}) {
  final panelHeight = switch (toolIndex) {
    kImageEditorToolPro => 420.0,
    kImageEditorToolText => 360.0,
    kImageEditorToolMosaic => 300.0,
    _ => 210.0,
  };
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
            selectedProCategory: selectedProCategory,
            proToolScrollController: ScrollController(),
            onSelectProCategory: (_) {},
            onExitProPanel: () {},
            onConfirmProPanel: () {},
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
            filterCatalogLoading: false,
            filterCatalogLoadFailed: false,
            onFilterCatalogRetry: () {},
            mosaicType: ImageEditorMosaicType.pixelate,
            mosaicBrushSize: 0.5,
            onMosaicTypeChanged: (_) {},
            onMosaicBrushSizeChanged: (_) {},
            mosaicHasStrokes: false,
            onMosaicUndoStroke: () {},
            textItems: selectedTextItem == null
                ? const <ImageEditorTextItem>[]
                : <ImageEditorTextItem>[selectedTextItem],
            selectedTextItem: selectedTextItem,
            onTextAdd: () {},
            onTextStyleChanged: onTextStyleChanged ?? (_) {},
            onTextColorChanged: (_) {},
            onTextDelete: onTextDelete ?? () {},
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
            curvesState: ImageEditorCurvesState(),
            curveChannel: ImageEditorCurveChannel.rgb,
            curveHistogram: null,
            onCurveChannelChanged: onCurveChannelChanged ?? (_) {},
            onCurvesChanged: (_) {},
            onCurveResetChannel: () {},
            wbTemperature: 0,
            wbTint: 0,
            onWbTemperatureChanged: (_) {},
            onWbTintChanged: (_) {},
            onWbAuto: onWbAuto ?? () {},
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
