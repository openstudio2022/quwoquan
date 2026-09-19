import 'package:flutter/services.dart';
import 'package:quwoquan_app/runtime/platform/media/generated/native_orientation_contract.g.dart';

export 'package:quwoquan_app/runtime/platform/media/generated/native_orientation_contract.g.dart';

/// 防腐边界只解码当前原生事实，不缓存成功值，也不把异常交给 Flutter 全局错误。
class NativeOrientationReader {
  const NativeOrientationReader({
    this.channel = const MethodChannel(nativeOrientationChannel),
  });
  final MethodChannel channel;

  Future<NativeOrientationObservation?> read() async {
    try {
      final value = NativeOrientationObservation.decode(
        await channel.invokeMethod<Object?>(nativeOrientationMethod),
      );
      return value.status == NativeOrientationStatus.available ? value : null;
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    } on FormatException {
      return null;
    }
  }
}
