import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_brand_cluster.dart';
import 'package:quwoquan_app/runtime/shell/welcome/welcome_flower_mark.dart';

/// 导出与 Flutter 欢迎终态同构的原生启动静态帧。
///
/// 布局与运行时共用 [WelcomeStaticFrame]（品牌簇视口分数对齐 + 贴底品牌名条），
/// 保证原生启动图与 Flutter 首帧几何同源。
///
/// 必须先加载正式品牌字体（Noto Sans SC）：widget test 默认无中文字形，
/// 否则 slogan / 品牌名会栅格成「豆腐块」方框并写进 Launch 位图。
///
/// 运行：`flutter test --no-pub tool/generate_native_launch_welcome_final_test.dart`
void main() {
  setUpAll(() async {
    final loader = FontLoader(AppTypography.welcomeBrandFontFamily)
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
    final footerBoundaryKey = GlobalKey();

    await tester.binding.setSurfaceSize(logicalSize);
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _buildWelcomeFinalFrameExport(
        logicalSize: logicalSize,
        boundaryKey: boundaryKey,
        backgroundBoundaryKey: backgroundBoundaryKey,
        brandBoundaryKey: brandBoundaryKey,
        footerBoundaryKey: footerBoundaryKey,
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    expect(find.text(FoundationText.welcomeMainSlogan), findsOneWidget);
    expect(find.text(FoundationText.welcomeTitle), findsOneWidget);
    expect(find.byType(WelcomeBrandCluster), findsOneWidget);
    expect(find.byType(WelcomeBrandFooter), findsOneWidget);

    final boundary =
        boundaryKey.currentContext!.findRenderObject()!
            as RenderRepaintBoundary;

    await tester.runAsync(() async {
      await _writeAndroidLaunchResources();
      final master = File('assets/brand/launch_welcome_final_master.png');
      final backgroundMaster = File(
        'assets/brand/launch_welcome_background_master.png',
      );
      final brandFullMaster = File(
        'assets/brand/launch_brand_cluster_full_master.png',
      );
      final footerMaster = File('assets/brand/launch_brand_footer_master.png');
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
      await _writeBoundary(
        footerBoundaryKey.currentContext!.findRenderObject()!
            as RenderRepaintBoundary,
        footerMaster.path,
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
      await _copy(
        footerMaster.path,
        'android/app/src/main/res/drawable-nodpi/launch_brand_footer.png',
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

      const iosFooter = 'ios/Runner/Assets.xcassets/LaunchBrandFooter.imageset';
      await _copy(footerMaster.path, '$iosFooter/LaunchBrandFooter@3x.png');
      await _resize(
        footerMaster.path,
        '$iosFooter/LaunchBrandFooter@2x.png',
        width: 786,
        height: 192,
      );
      await _resize(
        footerMaster.path,
        '$iosFooter/LaunchBrandFooter.png',
        width: 393,
        height: 96,
      );
    });

    // Android 的 layer-list 不能像 Flutter 一样用布局约束重新计算品牌簇。
    // 因此为常见手机宽度导出同一 WelcomeStaticFrame 的限定符资源；未知宽度
    // 由 Android 的资源选择回退到最接近的同源档，而不是拉伸 393dp 栅格。
    for (final bucket in _androidResponsiveBuckets) {
      await tester.binding.setSurfaceSize(bucket.logicalSize);
      await tester.pumpWidget(
        _buildWelcomeFinalFrameExport(
          logicalSize: bucket.logicalSize,
          boundaryKey: boundaryKey,
          backgroundBoundaryKey: backgroundBoundaryKey,
          brandBoundaryKey: brandBoundaryKey,
          footerBoundaryKey: footerBoundaryKey,
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 16));
      await tester.runAsync(() async {
        final scratch = await Directory.systemTemp.createTemp(
          'qwq-native-launch-${bucket.width}dp-',
        );
        try {
          final clusterMaster = scratch.path + '/cluster.png';
          final footerMaster = scratch.path + '/footer.png';
          await _writeBoundary(
            brandBoundaryKey.currentContext!.findRenderObject()!
                as RenderRepaintBoundary,
            clusterMaster,
          );
          await _writeBoundary(
            footerBoundaryKey.currentContext!.findRenderObject()!
                as RenderRepaintBoundary,
            footerMaster,
          );
          await _writeAndroidResponsiveBucketResources(
            bucket: bucket,
            clusterMaster: clusterMaster,
            footerMaster: footerMaster,
          );
        } finally {
          await scratch.delete(recursive: true);
        }
      });
    }
  });
}

class _AndroidResponsiveBucket {
  const _AndroidResponsiveBucket({
    required this.width,
    required this.height,
  });

  final int width;
  final int height;

  Size get logicalSize => Size(width.toDouble(), height.toDouble());

  int get footerHeight => WelcomeBrandFooter.resolveStripHeight(
    viewportHeight: height.toDouble(),
    bottomInset: 0,
  ).round();
}

const _androidResponsiveBuckets = <_AndroidResponsiveBucket>[
  _AndroidResponsiveBucket(width: 360, height: 800),
  _AndroidResponsiveBucket(width: 393, height: 852),
  _AndroidResponsiveBucket(width: 430, height: 932),
];

Widget _buildWelcomeFinalFrameExport({
  required Size logicalSize,
  required GlobalKey boundaryKey,
  required GlobalKey backgroundBoundaryKey,
  required GlobalKey brandBoundaryKey,
  required GlobalKey footerBoundaryKey,
}) {
  return MediaQuery(
    data: MediaQueryData(
      size: logicalSize,
      // 不烘焙假 SafeArea：与 Flutter WelcomeStaticFrame 分数对齐同构。
      padding: EdgeInsets.zero,
      devicePixelRatio: 1,
    ),
    child: CupertinoApp(
      theme: const CupertinoThemeData(
        textTheme: CupertinoTextThemeData(
          textStyle: TextStyle(
            fontFamily: AppTypography.welcomeBrandFontFamily,
            decoration: TextDecoration.none,
          ),
        ),
      ),
      home: RepaintBoundary(
        key: boundaryKey,
        child: _WelcomeFinalFrameExport(
          backgroundKey: backgroundBoundaryKey,
          brandKey: brandBoundaryKey,
          footerKey: footerBoundaryKey,
        ),
      ),
    ),
  );
}

class _WelcomeFinalFrameExport extends StatelessWidget {
  const _WelcomeFinalFrameExport({
    required this.backgroundKey,
    required this.brandKey,
    required this.footerKey,
  });

  final GlobalKey backgroundKey;
  final GlobalKey brandKey;
  final GlobalKey footerKey;

  @override
  Widget build(BuildContext context) {
    return DefaultTextStyle.merge(
      style: const TextStyle(
        fontFamily: AppTypography.welcomeBrandFontFamily,
        decoration: TextDecoration.none,
      ),
      child: ColoredBox(
        color: const Color(0x00000000),
        child: WelcomeStaticFrame(
          flower: WelcomeFlowerMark(appearance: WelcomeAppearance.of(context)),
          backgroundBoundaryKey: backgroundKey,
          clusterBoundaryKey: brandKey,
          footerBoundaryKey: footerKey,
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

Future<void> _copy(String source, String target) async {
  final file = File(target);
  await file.parent.create(recursive: true);
  await File(source).copy(file.path);
}

Future<void> _writeAndroidLaunchResources() async {
  final launchBackground =
      '''<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by generate_native_launch_welcome_final_test.dart. DO NOT EDIT. -->
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="270"
                android:centerColor="${_hexRgb(AppColors.welcomeBackground)}"
                android:endColor="${_hexRgb(AppColors.welcomeGradientEnd)}"
                android:startColor="${_hexRgb(AppColors.welcomeGradientStart)}" />
        </shape>
    </item>
    <item
        android:width="393dp"
        android:height="500dp"
        android:gravity="center">
        <bitmap
            android:gravity="fill"
            android:src="@drawable/launch_brand_cluster" />
    </item>
    <item
        android:width="393dp"
        android:height="96dp"
        android:gravity="bottom|center_horizontal">
        <bitmap
            android:gravity="fill"
            android:src="@drawable/launch_brand_footer" />
    </item>
</layer-list>
''';
  for (final path in const <String>[
    'android/app/src/main/res/drawable/launch_background.xml',
    'android/app/src/main/res/drawable-v21/launch_background.xml',
    'android/app/src/main/res/drawable-night/launch_background.xml',
    'android/app/src/main/res/drawable-night-v21/launch_background.xml',
  ]) {
    await File(path).writeAsString(launchBackground, flush: true);
  }

  final colors =
      '''<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by generate_native_launch_welcome_final_test.dart. DO NOT EDIT. -->
<resources>
    <color name="quwoquan_launch_blue">${_hexRgb(AppColors.welcomeBackground)}</color>
</resources>
''';
  await File(
    'android/app/src/main/res/values/colors.xml',
  ).writeAsString(colors, flush: true);
}

Future<void> _writeAndroidResponsiveBucketResources({
  required _AndroidResponsiveBucket bucket,
  required String clusterMaster,
  required String footerMaster,
}) async {
  final resourceQualifier = 'sw${bucket.width}dp';
  final clusterHeight = 500;
  final launchBackground = _androidLaunchBackgroundXml(
    width: bucket.width,
    clusterHeight: clusterHeight,
    footerHeight: bucket.footerHeight,
  );
  for (final directory in <String>[
    'drawable-$resourceQualifier',
    'drawable-$resourceQualifier-v21',
    'drawable-$resourceQualifier-night',
    'drawable-$resourceQualifier-night-v21',
  ]) {
    await File('android/app/src/main/res/$directory/launch_background.xml')
        .create(recursive: true)
        .then((file) => file.writeAsString(launchBackground, flush: true));
  }
  final imageDirectory =
      'android/app/src/main/res/drawable-$resourceQualifier-nodpi';
  await _centerCrop(
    clusterMaster,
    '$imageDirectory/launch_brand_cluster.png',
    width: bucket.width * 3,
    height: clusterHeight * 3,
  );
  await _resize(
    footerMaster,
    '$imageDirectory/launch_brand_footer.png',
    width: bucket.width * 3,
    height: bucket.footerHeight * 3,
  );
}

String _androidLaunchBackgroundXml({
  required int width,
  required int clusterHeight,
  required int footerHeight,
}) =>
    '''<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by generate_native_launch_welcome_final_test.dart. DO NOT EDIT. -->
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item>
        <shape android:shape="rectangle">
            <gradient
                android:angle="270"
                android:centerColor="${_hexRgb(AppColors.welcomeBackground)}"
                android:endColor="${_hexRgb(AppColors.welcomeGradientEnd)}"
                android:startColor="${_hexRgb(AppColors.welcomeGradientStart)}" />
        </shape>
    </item>
    <item
        android:width="${width}dp"
        android:height="${clusterHeight}dp"
        android:gravity="center">
        <bitmap
            android:gravity="fill"
            android:src="@drawable/launch_brand_cluster" />
    </item>
    <item
        android:width="${width}dp"
        android:height="${footerHeight}dp"
        android:gravity="bottom|center_horizontal">
        <bitmap
            android:gravity="fill"
            android:src="@drawable/launch_brand_footer" />
    </item>
</layer-list>
''';

String _hexRgb(ui.Color color) {
  final value = color.toARGB32() & 0x00FFFFFF;
  return '#${value.toRadixString(16).padLeft(6, '0').toUpperCase()}';
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
