import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// 联系人二维码相册识别边界。
///
/// UI 只关心「从本地图片里提取原始二维码 payload」，后续仍统一交
/// [QrPayloadParser] 与 `ResolveProfileQrToken` 校验，禁止端侧自解析直跳。
abstract class ContactQrImageAnalyzer {
  Future<String> analyzeImage({required String path});
}

class MobileScannerContactQrImageAnalyzer implements ContactQrImageAnalyzer {
  const MobileScannerContactQrImageAnalyzer();

  @override
  Future<String> analyzeImage({required String path}) async {
    final controller = MobileScannerController();
    try {
      final capture = await controller.analyzeImage(path);
      if (capture == null || capture.barcodes.isEmpty) {
        return '';
      }
      return capture.barcodes.first.rawValue?.trim() ?? '';
    } finally {
      unawaited(controller.dispose());
    }
  }
}

final contactQrImageAnalyzerProvider = Provider<ContactQrImageAnalyzer>((ref) {
  return const MobileScannerContactQrImageAnalyzer();
});
