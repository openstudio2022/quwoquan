import Flutter
import UIKit

/// 只绑定真实 Flutter window；每次读取当前 scene，不使用全局首个 scene。
final class NativeOrientationReader {
  private weak var window: UIWindow?
  private weak var scene: UIWindowScene?
  private var binding = UUID().uuidString
  private var observers: [NSObjectProtocol] = []

  init() {
    for name in [UIScene.willDeactivateNotification, UIScene.didDisconnectNotification] {
      observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] notification in
        guard let self = self, let scene = notification.object as? UIWindowScene,
              scene === self.window?.windowScene else { return }
        self.binding = UUID().uuidString
      })
    }
  }

  deinit { for observer in observers { NotificationCenter.default.removeObserver(observer) } }

  func attach(_ window: UIWindow) {
    if self.window !== window || scene !== window.windowScene { binding = UUID().uuidString }
    self.window = window
    scene = window.windowScene
  }

  func register(binaryMessenger: FlutterBinaryMessenger, editing: @escaping (FlutterMethodCall, @escaping FlutterResult) -> Void) {
    let channel = FlutterMethodChannel(name: NativeOrientationContract.channel, binaryMessenger: binaryMessenger)
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self = self else { result(FlutterMethodNotImplemented); return }
      if call.method == NativeOrientationContract.method {
        result(self.read())
      } else {
        editing(call, result)
      }
    }
  }

  func read() -> [String: Any] {
    var result: [String: Any] = [
      NativeOrientationContract.field_status: NativeOrientationContract.value_unavailable,
      NativeOrientationContract.field_platform: NativeOrientationContract.value_ios
    ]
    guard Thread.isMainThread, let window = window, !window.isHidden,
          window.rootViewController is FlutterViewController,
          let scene = window.windowScene, scene === self.scene,
          scene.activationState == .foregroundActive else { return result }
    let orientation: String
    switch scene.interfaceOrientation {
    case .portrait: orientation = NativeOrientationContract.value_portraitUp
    case .portraitUpsideDown: orientation = NativeOrientationContract.value_portraitDown
    case .landscapeLeft: orientation = NativeOrientationContract.value_landscapeLeft
    case .landscapeRight: orientation = NativeOrientationContract.value_landscapeRight
    default: return result
    }
    result[NativeOrientationContract.field_status] = NativeOrientationContract.value_available
    result[NativeOrientationContract.field_binding] = binding
    result[NativeOrientationContract.field_orientation] = orientation
    return result
  }
}
