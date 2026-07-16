import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('全平台应用图标与生成清单保持一致', () async {
    final manifestFile = File('assets/brand/app_icon_asset_manifest.json');
    expect(manifestFile.existsSync(), isTrue);
    final manifest = jsonDecode(await manifestFile.readAsString()) as Map;
    expect(manifest['schemaVersion'], 1);
    expect(manifest['source'], 'WelcomeAppIconPainter');

    final assets = (manifest['assets'] as Map).cast<String, String>();
    expect(assets.keys, containsAll(_requiredIconAssets.keys));
    for (final entry in assets.entries) {
      final file = File(entry.key);
      expect(file.existsSync(), isTrue, reason: entry.key);
      expect(
        sha256.convert(await file.readAsBytes()).toString(),
        entry.value,
        reason: '${entry.key} 已偏离共享品牌 Painter 的生成结果',
      );
    }
  });

  test('应用图标尺寸正确且最小尺寸仍有清晰花蕊', () async {
    for (final entry in _requiredIconAssets.entries) {
      final pixels = await _decodePng(entry.key);
      expect(pixels.width, entry.value, reason: entry.key);
      expect(pixels.height, entry.value, reason: entry.key);

      final center = pixels.pixelAt(pixels.width ~/ 2, pixels.height ~/ 2);
      final corner = pixels.pixelAt(0, 0);
      expect(center.alpha, 255, reason: entry.key);
      expect(
        center.luma,
        greaterThan(corner.luma + 35),
        reason: '${entry.key} 中心花蕊应明显亮于品牌蓝背景',
      );
    }
  });
}

const _requiredIconAssets = <String, int>{
  'assets/brand/app_icon_1024.png': 1024,
  'android/app/src/main/res/mipmap-mdpi/ic_launcher.png': 48,
  'ios/Runner/Assets.xcassets/AppIcon.appiconset/Icon-App-20x20@1x.png': 20,
  'web/icons/Icon-192.png': 192,
  'web/icons/Icon-512.png': 512,
  'web/icons/Icon-maskable-192.png': 192,
  'web/icons/Icon-maskable-512.png': 512,
  'web/favicon.png': 32,
};

Future<_DecodedPixels> _decodePng(String path) async {
  final bytes = await File(path).readAsBytes();
  final codec = await ui.instantiateImageCodec(bytes);
  final frame = await codec.getNextFrame();
  final data = await frame.image.toByteData(format: ui.ImageByteFormat.rawRgba);
  expect(data, isNotNull, reason: path);
  return _DecodedPixels(
    width: frame.image.width,
    height: frame.image.height,
    bytes: data!.buffer.asUint8List(),
  );
}

class _DecodedPixels {
  const _DecodedPixels({
    required this.width,
    required this.height,
    required this.bytes,
  });

  final int width;
  final int height;
  final List<int> bytes;

  _Rgba pixelAt(int x, int y) {
    final offset = (y * width + x) * 4;
    return _Rgba(
      red: bytes[offset],
      green: bytes[offset + 1],
      blue: bytes[offset + 2],
      alpha: bytes[offset + 3],
    );
  }
}

class _Rgba {
  const _Rgba({
    required this.red,
    required this.green,
    required this.blue,
    required this.alpha,
  });

  final int red;
  final int green;
  final int blue;
  final int alpha;

  double get luma => 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}
