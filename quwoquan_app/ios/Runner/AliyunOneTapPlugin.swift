import Flutter
import UIKit

/// 阿里云号码认证可选二进制防腐层。缺少控制台 SDK 或方案密钥时严格关闭能力。
final class AliyunOneTapPlugin {
  private let secretInfo: String
  private var initialized = false
  private var pendingResult: FlutterResult?

  init() {
    secretInfo =
      (Bundle.main.object(forInfoDictionaryKey: "QWQAliyunPNVSSecretInfo") as? String ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard isConfigured(secretInfo), AliyunOneTapRuntimeBridge.isSDKPresent() else {
      return
    }
    AliyunOneTapRuntimeBridge.configure(
      withSecretInfo: secretInfo
    ) { [weak self] response in
      self?.initialized = Self.resultCode(response) == "600000"
    }
  }

  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "isAvailable":
      result(initialized)
    case "probe":
      result([
        // 当前桥接层只能在拉起授权页后取得 token，尚不能在入口解析阶段形成
        // 完整可提交凭据；显式返回 invalidProbe，Flutter 必须隐藏入口并走短信。
        "availability": initialized
          ? "invalidProbe"
          : (isConfigured(secretInfo) ? "sdkUnavailable" : "notConfigured"),
        "vendor": initialized ? "aliyun" : "",
        "reason": initialized ? "prelogin_token_not_resolved" : "sdk_not_ready",
      ])
    case "requestLoginToken":
      requestLoginToken(result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func requestLoginToken(result: @escaping FlutterResult) {
    guard initialized, let controller = topViewController() else {
      result(FlutterError(
        code: "one_tap_sdk_not_configured",
        message: "One-tap login SDK is not configured for this build.",
        details: nil
      ))
      return
    }
    guard pendingResult == nil else {
      result(FlutterError(code: "one_tap_busy", message: "One-tap login is busy.", details: nil))
      return
    }
    pendingResult = result
    AliyunOneTapRuntimeBridge.requestLoginToken(
      from: controller
    ) { [weak self] response in
      self?.complete(response: response)
    }
  }

  private func complete(response: [String: Any]) {
    guard let result = pendingResult else { return }
    pendingResult = nil
    let code = Self.resultCode(response)
    let token = (response["token"] as? String ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if code == "600000", !token.isEmpty {
      result(["vendor": "aliyun", "carrierToken": token])
      return
    }
    let message = String(describing: response["msg"] ?? "").lowercased()
    result(FlutterError(
      code: message.contains("cancel") ? "one_tap_cancelled" : "one_tap_failed",
      message: "One-tap login failed.",
      details: nil
    ))
  }

  private func topViewController() -> UIViewController? {
    let root = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap(\.windows)
      .first(where: \.isKeyWindow)?
      .rootViewController
    var current = root
    while let presented = current?.presentedViewController {
      current = presented
    }
    return current
  }

  private func isConfigured(_ value: String) -> Bool {
    !value.isEmpty && !value.contains("$(")
  }

  private static func resultCode(_ response: [String: Any]) -> String {
    String(describing: response["resultCode"] ?? "")
  }
}
