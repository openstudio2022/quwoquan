import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_brand_cluster.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

/// 导出与 Flutter 欢迎终态同构的原生启动静态帧。
///
/// 必须先加载 Noto Sans SC：widget test 默认无中文字形，否则标题/slogan 会栅格成
/// 「豆腐块」方框并写进 Launch 位图。
///
/// 布局与运行时共用 [WelcomeBrandCluster]（视口分数对齐，不烘焙 SafeArea 顶 inset）。
///
/// 运行：`flutter test --no-pub tool/generate_native_launch_welcome_final_test.dart`
void main() {
  setUpAll(() async {
    final loader = FontLoader('Noto Sans SC')
      ..addFont(
        rootBundle.load('assets/fonts/noto_sans_sc/NotoSansSC[wght].ttf'),
      );
    await loader.load();
  });

  testWidgets('generate native launch welcome final-frame assets', (
    tester,
  ) async {
    const logicalSize = Size(393, 852);
    final boundaryKey = GlobalKey();
    final backgroundBoundaryKey = GlobalKey();
    final brandBoundaryKey = GlobalKey();

    await tester.binding.setSurfaceSize(logicalSize);
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      MediaQuery(
        data: const MediaQueryData(
          size: logicalSize,
          // 不烘焙假 SafeArea：与 Flutter WelcomeBrandCluster 分数对齐同构。
          padding: EdgeInsets.zero,
          devicePixelRatio: 1,
        ),
        child: CupertinoApp(
          theme: const CupertinoThemeData(
            textTheme: CupertinoTextThemeData(
              textStyle: TextStyle(
                fontFamily: 'Noto Sans SC',
                decoration: TextDecoration.none,
              ),
            ),
          ),
          home: RepaintBoundary(
            key: boundaryKey,
            child: _WelcomeFinalFrameExport(
              backgroundKey: backgroundBoundaryKey,
              brandKey: brandBoundaryKey,
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    expect(find.text(UITextConstants.welcomeTitle), findsOneWidget);
    expect(find.text(UITextConstants.welcomeMainSlogan), findsOneWidget);
    expect(find.byType(WelcomeBrandCluster), findsOneWidget);

    final boundary =
        boundaryKey.currentContext!.findRenderObject()!
            as RenderRepaintBoundary;

    await tester.runAsync(() async {
      final master = File('assets/brand/launch_welcome_final_master.png');
      final backgroundMaster = File(
        'assets/brand/launch_welcome_background_master.png',
      );
      final brandFullMaster = File(
        'assets/brand/launch_brand_cluster_full_master.png',
      );
      await _writeBoundary(boundary, master.path);
      await _writeBoundary(
        backgroundBoundaryKey.currentContext!.findRenderObject()!
            as RenderRepaintBoundary,
        backgroundMaster.path,
      );
      await _writeBoundary(
        brandBoundaryKey.currentContext!.findRenderObject()!
            as RenderRepaintBoundary,
        brandFullMaster.path,
      );

      await _resize(
        master.path,
        'android/app/src/main/res/drawable-nodpi/launch_welcome_final.png',
        width: 1179,
        height: 2556,
      );
      await _centerCrop(
        brandFullMaster.path,
        'android/app/src/main/res/drawable-nodpi/launch_brand_cluster.png',
        width: 1179,
        height: 1500,
      );

      const iosBg =
          'ios/Runner/Assets.xcassets/LaunchTransitionBackground.imageset';
      await _resize(
        backgroundMaster.path,
        '$iosBg/LaunchTransitionBackground.png',
        width: 1,
        height: 3,
      );
      await _resize(
        backgroundMaster.path,
        '$iosBg/LaunchTransitionBackground@2x.png',
        width: 2,
        height: 6,
      );
      await _resize(
        backgroundMaster.path,
        '$iosBg/LaunchTransitionBackground@3x.png',
        width: 3,
        height: 9,
      );

      const iosLaunch = 'ios/Runner/Assets.xcassets/LaunchImage.imageset';
      await _resize(
        backgroundMaster.path,
        '$iosLaunch/LaunchImage.png',
        width: 1,
        height: 3,
      );
      await _resize(
        backgroundMaster.path,
        '$iosLaunch/LaunchImage@2x.png',
        width: 2,
        height: 6,
      );
      await _resize(
        backgroundMaster.path,
        '$iosLaunch/LaunchImage@3x.png',
        width: 3,
        height: 9,
      );

      final brand3x = File(
        'ios/Runner/Assets.xcassets/LaunchBrandCluster.imageset/'
        'LaunchBrandCluster@3x.png',
      );
      await _centerCrop(
        brandFullMaster.path,
        brand3x.path,
        width: 1179,
        height: 1500,
      );
      await _resize(
        brand3x.path,
        'ios/Runner/Assets.xcassets/LaunchBrandCluster.imageset/'
        'LaunchBrandCluster@2x.png',
        width: 786,
        height: 1000,
      );
      await _resize(
        brand3x.path,
        'ios/Runner/Assets.xcassets/LaunchBrandCluster.imageset/'
        'LaunchBrandCluster.png',
        width: 393,
        height: 500,
      );
    });
  });
}

class _WelcomeFinalFrameExport extends StatelessWidget {
  const _WelcomeFinalFrameExport({
    required this.backgroundKey,
    required this.brandKey,
  });

  static const List<double> _fullBloom = [1, 1, 1, 1, 1, 1, 1, 1];
  static const String _fontFamily = 'Noto Sans SC';
  final GlobalKey backgroundKey;
  final GlobalKey brandKey;

  @override
  Widget build(BuildContext context) {
    final appearance = WelcomeAppearance.of(context);
    return DefaultTextStyle.merge(
      style: const TextStyle(
        fontFamily: _fontFamily,
        decoration: TextDecoration.none,
      ),
      child: ColoredBox(
        color: const Color(0x00000000),
        child: Stack(
          fit: StackFit.expand,
          children: [
            RepaintBoundary(
              key: backgroundKey,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: [
                      appearance.gradientStart,
                      appearance.background,
                      appearance.gradientEnd,
                    ],
                  ),
                ),
              ),
            ),
            RepaintBoundary(
              key: brandKey,
              child: WelcomeBrandCluster(
                flower: WelcomeFlowerMark(
                  appearance: appearance,
                  petalBloomAmounts: _fullBloom,
                ),
                typography: WelcomeBrandCluster.buildTypography(
                  appearance,
                  fontFamily: _fontFamily,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

Future<void> _writeBoundary(
  RenderRepaintBoundary boundary,
  String target,
) async {
  final image = await boundary.toImage(pixelRatio: 3);
  final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
  final file = File(target);
  await file.create(recursive: true);
  await file.writeAsBytes(byteData!.buffer.asUint8List(), flush: true);
}

Future<void> _resize(
  String source,
  String target, {
  required int width,
  required int height,
}) async {
  await File(target).parent.create(recursive: true);
  final result = await Process.run('sips', [
    '-z',
    '$height',
    '$width',
    source,
    '--out',
    target,
  ]);
  if (result.exitCode != 0) {
    throw ProcessException(
      'sips',
      ['-z', '$height', '$width', source, '--out', target],
      '${result.stdout}\n${result.stderr}',
      result.exitCode,
    );
  }
}

Future<void> _centerCrop(
  String source,
  String target, {
  required int width,
  required int height,
}) async {
  await File(target).parent.create(recursive: true);
  final result = await Process.run('sips', [
    '-c',
    '$height',
    '$width',
    source,
    '--out',
    target,
  ]);
  if (result.exitCode != 0) {
    throw ProcessException(
      'sips',
      ['-c', '$height', '$width', source, '--out', target],
      '${result.stdout}\n${result.stderr}',
      result.exitCode,
    );
  }
}
