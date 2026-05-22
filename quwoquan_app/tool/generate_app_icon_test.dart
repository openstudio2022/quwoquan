import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

void main() {
  testWidgets('generate launcher icons from welcome flower painter', (
    tester,
  ) async {
    const iconSize = Size.square(1024);
    final boundaryKey = GlobalKey();

    await tester.binding.setSurfaceSize(iconSize);
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      CupertinoApp(
        home: RepaintBoundary(
          key: boundaryKey,
          child: SizedBox.fromSize(
            size: iconSize,
            child: Builder(
              builder: (context) {
                return CustomPaint(
                  painter: WelcomeAppIconPainter(
                    appearance: WelcomeAppearance.of(context),
                    flowerDiameterRatio: 0.75,
                  ),
                );
              },
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    final boundary =
        boundaryKey.currentContext!.findRenderObject()!
            as RenderRepaintBoundary;

    await tester.runAsync(() async {
      final image = await boundary.toImage(pixelRatio: 1);
      final byteData = await image.toByteData(format: ui.ImageByteFormat.png);
      final bytes = byteData!.buffer.asUint8List();

      final master = File('assets/brand/app_icon_1024.png');
      await master.create(recursive: true);
      await master.writeAsBytes(bytes, flush: true);
      await File(
        'assets/brand/app_icon_square.png',
      ).writeAsBytes(bytes, flush: true);

      await _resize(
        master.path,
        'android/app/src/main/res/mipmap-mdpi/ic_launcher.png',
        48,
      );
      await _resize(
        master.path,
        'android/app/src/main/res/mipmap-hdpi/ic_launcher.png',
        72,
      );
      await _resize(
        master.path,
        'android/app/src/main/res/mipmap-xhdpi/ic_launcher.png',
        96,
      );
      await _resize(
        master.path,
        'android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png',
        144,
      );
      await _resize(
        master.path,
        'android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png',
        192,
      );

      const iosIconDir = 'ios/Runner/Assets.xcassets/AppIcon.appiconset';
      await _resize(master.path, '$iosIconDir/Icon-App-20x20@1x.png', 20);
      await _resize(master.path, '$iosIconDir/Icon-App-20x20@2x.png', 40);
      await _resize(master.path, '$iosIconDir/Icon-App-20x20@3x.png', 60);
      await _resize(master.path, '$iosIconDir/Icon-App-29x29@1x.png', 29);
      await _resize(master.path, '$iosIconDir/Icon-App-29x29@2x.png', 58);
      await _resize(master.path, '$iosIconDir/Icon-App-29x29@3x.png', 87);
      await _resize(master.path, '$iosIconDir/Icon-App-40x40@1x.png', 40);
      await _resize(master.path, '$iosIconDir/Icon-App-40x40@2x.png', 80);
      await _resize(master.path, '$iosIconDir/Icon-App-40x40@3x.png', 120);
      await _resize(master.path, '$iosIconDir/Icon-App-60x60@2x.png', 120);
      await _resize(master.path, '$iosIconDir/Icon-App-60x60@3x.png', 180);
      await _resize(master.path, '$iosIconDir/Icon-App-76x76@1x.png', 76);
      await _resize(master.path, '$iosIconDir/Icon-App-76x76@2x.png', 152);
      await _resize(master.path, '$iosIconDir/Icon-App-83.5x83.5@2x.png', 167);
      await _resize(master.path, '$iosIconDir/Icon-App-1024x1024@1x.png', 1024);
    });
  });
}

Future<void> _resize(String source, String target, int size) async {
  await File(target).parent.create(recursive: true);
  final result = await Process.run('sips', [
    '-z',
    '$size',
    '$size',
    source,
    '--out',
    target,
  ]);
  if (result.exitCode != 0) {
    throw ProcessException(
      'sips',
      ['-z', '$size', '$size', source, '--out', target],
      '${result.stdout}\n${result.stderr}',
      result.exitCode,
    );
  }
}
