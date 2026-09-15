// Flutter channel adapter for the native runtime config supply stack.

import Flutter
import Foundation

/// Dart 侧 `native_runtime_config_bridge` 的原生对端。
///
/// 注册逻辑与 channel 名同样只有一份：两个 target 的 AppDelegate 都调用本函数，
/// 因此 test host 不会出现「注册了同名 channel 但语义不同」的第二实现。
enum NativeRuntimeConfigChannel {
  static let name = "quwoquan/runtime/config"

  static func register(binaryMessenger: FlutterBinaryMessenger) {
    let runtimeConfigChannel = FlutterMethodChannel(
      name: name,
      binaryMessenger: binaryMessenger
    )
    runtimeConfigChannel.setMethodCallHandler { call, result in
      DispatchQueue.global(qos: .userInitiated).async {
        do {
          let response: Any
          switch call.method {
          case "readRuntimeConfig":
            response = try NativeRuntimeConfigStore.readRuntimeConfig()
          case "readRuntimeConfigState":
            response = NativeRuntimeConfigStore.readRuntimeConfigState()
          default:
            DispatchQueue.main.async { result(FlutterMethodNotImplemented) }
            return
          }
          DispatchQueue.main.async { result(response) }
        } catch let error as NativeRuntimeConfigReadError {
          DispatchQueue.main.async {
            result(FlutterError(
              code: error.flutterCode,
              message: "Native runtime configuration operation failed.",
              details: nil
            ))
          }
        } catch {
          let internalFailure = nativeRuntimeConfigInternalFailure(
            context: "flutter_runtime_config_channel",
            error: error
          )
          DispatchQueue.main.async {
            result(FlutterError(
              code: internalFailure.flutterCode,
              message: "Native runtime configuration operation failed.",
              details: nil
            ))
          }
        }
      }
    }
  }
}
