import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

void main() {
  testWidgets('PageflipWidget pumps and renders the current page', (
    WidgetTester tester,
  ) async {
    final engine = PageflipEngine(pageCount: 4, initialPage: 1);

    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox.expand(
          child: PageflipWidget(
            engine: engine,
            pageBuilder: (context, pageIndex) => Center(
              child: Text('page-$pageIndex'),
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('page-1'), findsOneWidget);
  });

  testWidgets('PageflipWidget uses long-form curl renderer during interaction', (
    WidgetTester tester,
  ) async {
    final engine = PageflipEngine(pageCount: 4, initialPage: 1);

    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox.expand(
          child: PageflipWidget(
            engine: engine,
            pageBuilder: (context, pageIndex) => ColoredBox(
              color: pageIndex.isEven ? Colors.amber : Colors.blue,
              child: Center(child: Text('page-$pageIndex')),
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    final gesture = await tester.startGesture(const Offset(700, 300));
    await gesture.moveBy(const Offset(-180, 0));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('pageflip_curl_renderer')), findsOneWidget);
    expect(find.byKey(const ValueKey('pageflip_fold_line')), findsNothing);
    expect(find.byKey(const ValueKey('pageflip_static_page_2')), findsOneWidget);
    expect(find.byKey(const ValueKey('pageflip_static_page_1')), findsNothing);
  });

  testWidgets('PageflipWidget switches static page to underlay while dragging', (
    WidgetTester tester,
  ) async {
    final engine = PageflipEngine(pageCount: 4, initialPage: 1);

    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox.expand(
          child: PageflipWidget(
            engine: engine,
            pageBuilder: (context, pageIndex) => ColoredBox(
              color: pageIndex.isEven ? Colors.amber : Colors.blue,
              child: Center(child: Text('page-$pageIndex')),
            ),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('pageflip_static_page_1')), findsOneWidget);

    final gesture = await tester.startGesture(const Offset(700, 300));
    await gesture.moveBy(const Offset(-120, 0));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('pageflip_static_page_1')), findsNothing);
    expect(find.byKey(const ValueKey('pageflip_static_page_2')), findsOneWidget);
    expect(find.byKey(const ValueKey('pageflip_curl_renderer')), findsOneWidget);
    expect(find.byKey(const ValueKey('pageflip_fold_line')), findsNothing);
  });

  testWidgets('PageflipDiagnosticsApp shows long-form baseline content', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const PageflipDiagnosticsApp());
    await tester.pumpAndSettle();

    expect(find.byType(FittedBox), findsNothing);
    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byType(PageflipWidget), findsOneWidget);
  });

  testWidgets(
    'a. mesh coverage keeps the fold band continuous across scanlines',
    (WidgetTester tester) async {
      final sample = await _renderForwardProbeScene(tester);
      expect(sample.seenRed, isTrue);
      expect(
        sample.maxWhiteRun,
        lessThanOrEqualTo(6),
        reason: 'a wide white band between front and back suggests a coverage gap',
      );
    },
  );

  testWidgets(
    'b. backface composition exposes the next-page surface before the front page',
    (WidgetTester tester) async {
      final sample = await _renderForwardProbeScene(tester);
      expect(sample.seenGreen, isTrue);
      expect(sample.firstRedX, greaterThanOrEqualTo(0));
      expect(sample.firstGreenX, greaterThanOrEqualTo(0));
      expect(
        sample.firstGreenX,
        lessThan(sample.firstRedX),
        reason: 'green backface should appear before the red front-page region',
      );
    },
  );
}

Future<_ForwardProbeSample> _renderForwardProbeScene(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(900, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final boundaryKey = GlobalKey();
  final engine = PageflipEngine(pageCount: 4, initialPage: 1);
  final pages = <Color>[
    const Color(0xFFE53935),
    const Color(0xFFE53935),
    const Color(0xFF43A047),
    const Color(0xFF1E88E5),
  ];

  await tester.pumpWidget(
    MaterialApp(
      home: RepaintBoundary(
        key: boundaryKey,
        child: SizedBox.expand(
          child: PageflipWidget(
            engine: engine,
            pageBuilder: (context, pageIndex) {
              return ColoredBox(
                color: pages[pageIndex],
                child: const SizedBox.expand(),
              );
            },
          ),
        ),
      ),
    ),
  );

  for (var i = 0; i < 6; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  final sceneBefore = engine.buildScene(const Size(900, 1200));
  expect(sceneBefore, isNotNull);

  final start = Offset(
    sceneBefore!.pageRect.right - 18,
    sceneBefore.pageRect.bottom - 18,
  );
  final gesture = await tester.startGesture(start);
  await gesture.moveBy(const Offset(-220, -22));
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final sceneAfter = engine.buildScene(const Size(900, 1200));
  expect(sceneAfter, isNotNull);
  expect(sceneAfter!.renderFrame, isNotNull);
  expect(sceneAfter.renderFrame!.direction, PageflipDirection.forward);

  final image = await _captureBoundaryImage(boundaryKey);
  final bytes = await _rawRgbaBytes(image);
  final left = sceneAfter.pageRect.left.round();
  final right = sceneAfter.pageRect.right.round();

  var seenRed = false;
  var seenGreen = false;
  var firstRedX = -1;
  var firstGreenX = -1;
  var maxWhiteRun = 0;

  final scanlineOffsets = <double>[-0.18, 0.0, 0.18];
  for (final offsetFactor in scanlineOffsets) {
    final scanline = (sceneAfter.pageRect.center.dy +
            sceneAfter.pageRect.height * offsetFactor)
        .round();
    final result = _scanForwardLine(
      imageWidth: image.width,
      imageHeight: image.height,
      bytes: bytes,
      left: left,
      right: right,
      scanlineY: scanline,
    );
    seenRed = seenRed || result.seenRed;
    seenGreen = seenGreen || result.seenGreen;
    maxWhiteRun = result.maxWhiteRun > maxWhiteRun ? result.maxWhiteRun : maxWhiteRun;
    if (offsetFactor == 0.0) {
      firstRedX = result.firstRedX;
      firstGreenX = result.firstGreenX;
    }
  }

  await gesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));

  return _ForwardProbeSample(
    seenRed: seenRed,
    seenGreen: seenGreen,
    firstRedX: firstRedX,
    firstGreenX: firstGreenX,
    maxWhiteRun: maxWhiteRun,
  );
}

_ScanlineProbeResult _scanForwardLine({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required int left,
  required int right,
  required int scanlineY,
}) {
  var seenRed = false;
  var seenGreen = false;
  var firstRedX = -1;
  var firstGreenX = -1;
  var whiteRun = 0;
  var maxWhiteRun = 0;

  for (var x = left; x <= right; x += 1) {
    final color = _colorAtBytes(
      imageWidth,
      imageHeight,
      bytes,
      Offset(x.toDouble(), scanlineY.toDouble()),
    );
    final classification = _classifyProbeColor(color);
    if (classification == _ProbeColor.red) {
      seenRed = true;
      firstRedX = firstRedX < 0 ? x : firstRedX;
    }
    if (classification == _ProbeColor.green) {
      seenGreen = true;
      firstGreenX = firstGreenX < 0 ? x : firstGreenX;
    }
    if (seenRed && classification == _ProbeColor.white) {
      whiteRun += 1;
      maxWhiteRun = whiteRun > maxWhiteRun ? whiteRun : maxWhiteRun;
    } else {
      whiteRun = 0;
    }
  }

  return _ScanlineProbeResult(
    seenRed: seenRed,
    seenGreen: seenGreen,
    firstRedX: firstRedX,
    firstGreenX: firstGreenX,
    maxWhiteRun: maxWhiteRun,
  );
}

Future<ui.Image> _captureBoundaryImage(GlobalKey boundaryKey) async {
  final context = boundaryKey.currentContext;
  expect(context, isNotNull);
  final renderObject = context!.findRenderObject();
  expect(renderObject, isA<RenderRepaintBoundary>());
  final boundary = renderObject as RenderRepaintBoundary;
  return boundary.toImage(pixelRatio: 1);
}

Future<Uint8List> _rawRgbaBytes(ui.Image image) async {
  final byteData = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  expect(byteData, isNotNull);
  return byteData!.buffer.asUint8List();
}

Color _colorAtBytes(
  int imageWidth,
  int imageHeight,
  Uint8List bytes,
  Offset offset,
) {
  final x = offset.dx.round().clamp(0, imageWidth - 1);
  final y = offset.dy.round().clamp(0, imageHeight - 1);
  final index = (y * imageWidth + x) * 4;
  return Color.fromARGB(
    bytes[index + 3],
    bytes[index],
    bytes[index + 1],
    bytes[index + 2],
  );
}

enum _ProbeColor { red, green, white, other }

_ProbeColor _classifyProbeColor(Color color) {
  if (color.red > 235 && color.green > 235 && color.blue > 235) {
    return _ProbeColor.white;
  }
  if (color.red > color.green + 40 && color.red > color.blue + 40) {
    return _ProbeColor.red;
  }
  if (color.green > color.red + 30 && color.green > color.blue + 20) {
    return _ProbeColor.green;
  }
  return _ProbeColor.other;
}

class _ForwardProbeSample {
  const _ForwardProbeSample({
    required this.seenRed,
    required this.seenGreen,
    required this.firstRedX,
    required this.firstGreenX,
    required this.maxWhiteRun,
  });

  final bool seenRed;
  final bool seenGreen;
  final int firstRedX;
  final int firstGreenX;
  final int maxWhiteRun;
}

class _ScanlineProbeResult {
  const _ScanlineProbeResult({
    required this.seenRed,
    required this.seenGreen,
    required this.firstRedX,
    required this.firstGreenX,
    required this.maxWhiteRun,
  });

  final bool seenRed;
  final bool seenGreen;
  final int firstRedX;
  final int firstGreenX;
  final int maxWhiteRun;
}
