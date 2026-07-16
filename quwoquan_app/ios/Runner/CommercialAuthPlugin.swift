import AlipaySDK
import Flutter
import UIKit
import WechatOpenSDK

/// 官方微信、支付宝、QQ SDK 到 Flutter NativeAuthBridge 的防腐层。
final class CommercialAuthPlugin: NSObject, WXApiDelegate, TencentSessionDelegate {
  static weak var shared: CommercialAuthPlugin?

  private let wechatAppID: String
  private let wechatUniversalLink: String
  private let qqAppID: String
  private let alipayCallbackScheme: String
  private var qqOAuth: TencentOAuth?
  private var pendingWechatResult: FlutterResult?
  private var pendingWechatState = ""
  private var pendingAlipayResult: FlutterResult?
  private var pendingQQResult: FlutterResult?
  private var didRegisterWechat = false

  override init() {
    wechatAppID = Self.configValue("QWQWechatAppID")
    wechatUniversalLink = Self.configValue("QWQWechatUniversalLink")
    qqAppID = Self.configValue("QWQQQAppID")
    alipayCallbackScheme = Self.configValue("QWQAlipayCallbackScheme")
    super.init()
    Self.shared = self
  }

  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    let arguments = call.arguments as? [String: Any] ?? [:]
    let provider = (arguments["provider"] as? String ?? "").trimmingCharacters(in: .whitespaces)
    switch call.method {
    case "getCapability":
      result(capability(provider: provider))
    case "signIn":
      signIn(
        provider: provider,
        authorizationPayload: arguments["authorizationPayload"] as? String ?? "",
        result: result
      )
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  func handle(url: URL) -> Bool {
    if WXApi.handleOpen(url, delegate: self) {
      return true
    }
    if TencentOAuth.handleOpen(url) {
      return true
    }
    guard
      isConfigured(alipayCallbackScheme),
      url.scheme == alipayCallbackScheme
    else {
      return false
    }
    AlipaySDK.defaultService().processAuth_V2Result(url) { [weak self] response in
      self?.completeAlipay(response)
    }
    return true
  }

  func handle(userActivity: NSUserActivity) -> Bool {
    WXApi.handleOpenUniversalLink(userActivity, delegate: self)
  }

  private func capability(provider: String) -> [String: Any] {
    let available: Bool
    let reason: String
    switch provider {
    case "wechat":
      available =
        isConfigured(wechatAppID) &&
        isConfigured(wechatUniversalLink) &&
        UIApplication.shared.canOpenURL(URL(string: "weixin://")!)
      reason = available ? "official_sdk" : "wechat_not_configured_or_installed"
    case "alipay":
      available =
        isConfigured(alipayCallbackScheme) &&
        UIApplication.shared.canOpenURL(URL(string: "alipay://")!)
      reason = available ? "official_sdk" : "alipay_not_configured_or_installed"
    case "qq":
      available =
        isConfigured(qqAppID) &&
        UIApplication.shared.canOpenURL(URL(string: "mqqapi://")!)
      reason = available ? "official_sdk" : "qq_not_configured_or_installed"
    default:
      available = false
      reason = "unsupported_provider"
    }
    return ["provider": provider, "available": available, "reason": reason]
  }

  private func signIn(
    provider: String,
    authorizationPayload: String,
    result: @escaping FlutterResult
  ) {
    guard capability(provider: provider)["available"] as? Bool == true else {
      result(FlutterError(
        code: "native_auth_unavailable",
        message: "Provider unavailable.",
        details: nil
      ))
      return
    }
    switch provider {
    case "wechat":
      signInWechat(result: result)
    case "alipay":
      signInAlipay(payload: authorizationPayload, result: result)
    case "qq":
      signInQQ(result: result)
    default:
      result(FlutterError(
        code: "native_auth_unavailable",
        message: "Provider unavailable.",
        details: nil
      ))
    }
  }

  private func signInWechat(result: @escaping FlutterResult) {
    guard pendingWechatResult == nil else {
      result(FlutterError(code: "native_auth_busy", message: "Authorization busy.", details: nil))
      return
    }
    pendingWechatResult = result
    pendingWechatState = UUID().uuidString.replacingOccurrences(of: "-", with: "")
    if !didRegisterWechat {
      didRegisterWechat = WXApi.registerApp(
        wechatAppID,
        universalLink: wechatUniversalLink
      )
    }
    guard didRegisterWechat else {
      pendingWechatResult = nil
      pendingWechatState = ""
      result(FlutterError(
        code: "native_auth_unavailable",
        message: "Unable to configure WeChat authorization.",
        details: nil
      ))
      return
    }
    let request = SendAuthReq()
    request.scope = "snsapi_userinfo"
    request.state = pendingWechatState
    WXApi.send(request) { [weak self] succeeded in
      guard !succeeded, let self else { return }
      self.pendingWechatResult = nil
      self.pendingWechatState = ""
      result(FlutterError(
        code: "native_auth_unavailable",
        message: "Unable to start WeChat authorization.",
        details: nil
      ))
    }
  }

  private func signInAlipay(payload: String, result: @escaping FlutterResult) {
    let trimmed = payload.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
      result(FlutterError(
        code: "native_auth_unavailable",
        message: "Alipay authorization payload unavailable.",
        details: nil
      ))
      return
    }
    guard pendingAlipayResult == nil else {
      result(FlutterError(code: "native_auth_busy", message: "Authorization busy.", details: nil))
      return
    }
    pendingAlipayResult = result
    AlipaySDK.defaultService().auth_V2(
      withInfo: trimmed,
      fromScheme: alipayCallbackScheme,
      callback: { [weak self] response in
        self?.completeAlipay(response)
      }
    )
  }

  private func completeAlipay(
    _ response: [AnyHashable: Any]?
  ) {
    guard let result = pendingAlipayResult else { return }
    pendingAlipayResult = nil
    let status = String(describing: response?["resultStatus"] ?? "")
    if status == "6001" {
      result(FlutterError(code: "native_auth_cancelled", message: "Authorization cancelled.", details: nil))
      return
    }
    let payload = String(describing: response?["result"] ?? "")
    guard
      status == "9000",
      let code = queryValue("auth_code", in: payload),
      !code.isEmpty
    else {
      result(FlutterError(code: "native_auth_failed", message: "Alipay authorization failed.", details: nil))
      return
    }
    result(ticketPayload(provider: "alipay", ticket: code))
  }

  private func signInQQ(result: @escaping FlutterResult) {
    guard pendingQQResult == nil else {
      result(FlutterError(code: "native_auth_busy", message: "Authorization busy.", details: nil))
      return
    }
    TencentOAuth.setIsUserAgreedAuthorization(true)
    if qqOAuth == nil {
      qqOAuth = TencentOAuth(appId: qqAppID, andDelegate: self)
    }
    guard let qqOAuth else {
      result(FlutterError(code: "native_auth_unavailable", message: "QQ unavailable.", details: nil))
      return
    }
    pendingQQResult = result
    qqOAuth.authorize([kOPEN_PERMISSION_GET_USER_INFO])
  }

  func onResp(_ response: BaseResp) {
    guard let result = pendingWechatResult, let authResponse = response as? SendAuthResp else {
      return
    }
    pendingWechatResult = nil
    defer { pendingWechatState = "" }
    if response.errCode == WXErrCodeUserCancel.rawValue {
      result(FlutterError(code: "native_auth_cancelled", message: "Authorization cancelled.", details: nil))
      return
    }
    guard
      response.errCode == WXSuccess.rawValue,
      authResponse.state == pendingWechatState,
      let code = authResponse.code?.trimmingCharacters(in: .whitespaces),
      !code.isEmpty
    else {
      result(FlutterError(code: "native_auth_failed", message: "WeChat authorization failed.", details: nil))
      return
    }
    result(ticketPayload(provider: "wechat", ticket: code))
  }

  func onReq(_ request: BaseReq) {}

  func tencentDidLogin() {
    guard let result = pendingQQResult, let qqOAuth else { return }
    pendingQQResult = nil
    let token = qqOAuth.accessToken ?? ""
    let openID = qqOAuth.openId ?? ""
    guard !token.isEmpty, !openID.isEmpty else {
      result(FlutterError(code: "native_auth_failed", message: "QQ authorization failed.", details: nil))
      return
    }
    let raw: [String: String] = ["accessToken": token, "openId": openID]
    guard
      let data = try? JSONSerialization.data(withJSONObject: raw),
      !data.isEmpty
    else {
      result(FlutterError(code: "native_auth_failed", message: "QQ authorization failed.", details: nil))
      return
    }
    result(ticketPayload(
      provider: "qq",
      ticket: "qq_mobile_v1." + data.base64URLEncodedString()
    ))
  }

  func tencentDidNotLogin(_ cancelled: Bool) {
    guard let result = pendingQQResult else { return }
    pendingQQResult = nil
    result(FlutterError(
      code: cancelled ? "native_auth_cancelled" : "native_auth_failed",
      message: cancelled ? "Authorization cancelled." : "QQ authorization failed.",
      details: nil
    ))
  }

  func tencentDidNotNetWork() {
    guard let result = pendingQQResult else { return }
    pendingQQResult = nil
    result(FlutterError(code: "native_auth_failed", message: "QQ authorization failed.", details: nil))
  }

  private func ticketPayload(provider: String, ticket: String) -> [String: Any] {
    ["provider": provider, "ticket": ticket]
  }

  private func queryValue(_ key: String, in raw: String) -> String? {
    let cleaned = raw
      .replacingOccurrences(of: "{", with: "")
      .replacingOccurrences(of: "}", with: "")
    return URLComponents(string: "https://localhost/?" + cleaned)?
      .queryItems?
      .first(where: { $0.name == key })?
      .value
  }

  private func isConfigured(_ value: String) -> Bool {
    !value.isEmpty && !value.contains("$(")
  }

  private static func configValue(_ key: String) -> String {
    (Bundle.main.object(forInfoDictionaryKey: key) as? String ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }
}

extension Data {
  fileprivate func base64URLEncodedString() -> String {
    base64EncodedString()
      .replacingOccurrences(of: "+", with: "-")
      .replacingOccurrences(of: "/", with: "_")
      .replacingOccurrences(of: "=", with: "")
  }
}
