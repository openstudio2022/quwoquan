import Foundation

// 原生启动恢复的访问分流与严格版本响应；不依赖 Flutter 或 UI 生命周期。
enum NativeRecoveryAccess: Equatable {
  case configuration, offline, remote

  static func resolve(activationFailed: Bool, configValid: Bool, networkAllowed: Bool) -> Self {
    if activationFailed || !configValid { return .configuration }
    return networkAllowed ? .remote : .offline
  }

  var allowsWeb: Bool { self == .remote }
}

enum NativeRecoveryUpdateState: String, Equatable {
  case none
  case available
  case required
}

struct NativeRecoveryVersionResponse: Equatable {
  private static let canonicalFields: Set<String> = [
    "platform",
    "latestVersion",
    "latestBuild",
    "minimumSupportedVersion",
    "minimumSupportedBuild",
    "updateState",
    "updateUrl",
    "recoveryUrl",
  ]

  let platform: String
  let latestVersion: String
  let latestBuild: Int
  let minimumSupportedVersion: String
  let minimumSupportedBuild: Int
  let updateState: NativeRecoveryUpdateState
  let updateURL: String?
  let recoveryURL: String

  var hasNewerVersion: Bool { updateState != .none }

  // 公众 iOS wire 明确没有原生更新通道；即使服务端判定 available/required，
  // 原生恢复页也只能进入 Web/PWA。
  var offersNativeUpdate: Bool {
    platform == "android" && hasNewerVersion && updateURL != nil
  }

  static func parse(
    payload: [String: Any],
    expectedPlatform: String,
    currentBuild: Int,
    isTrustedURL: (URL?) -> Bool
  ) -> NativeRecoveryVersionResponse? {
    guard Set(payload.keys) == canonicalFields,
          currentBuild > 0,
          payload["platform"] as? String == expectedPlatform,
          let latestVersion = nonBlankString(payload["latestVersion"]),
          let latestBuild = positiveDecimal(payload["latestBuild"]),
          let minimumSupportedVersion = nonBlankString(
            payload["minimumSupportedVersion"]
          ),
          let minimumSupportedBuild = positiveDecimal(
            payload["minimumSupportedBuild"]
          ),
          minimumSupportedBuild <= latestBuild,
          let updateStateRaw = payload["updateState"] as? String,
          let updateState = NativeRecoveryUpdateState(rawValue: updateStateRaw),
          let recoveryURL = nonBlankString(payload["recoveryUrl"]),
          isTrustedURL(URL(string: recoveryURL))
    else {
      return nil
    }
    let expectedUpdateState: NativeRecoveryUpdateState
    if currentBuild < minimumSupportedBuild {
      expectedUpdateState = .required
    } else if currentBuild < latestBuild {
      expectedUpdateState = .available
    } else {
      expectedUpdateState = .none
    }
    guard updateState == expectedUpdateState else { return nil }

    let updateURL: String?
    switch expectedPlatform {
    case "ios":
      guard payload["updateUrl"] is NSNull else { return nil }
      updateURL = nil
    case "android":
      guard let rawUpdateURL = nonBlankString(payload["updateUrl"]),
            isTrustedURL(URL(string: rawUpdateURL))
      else {
        return nil
      }
      updateURL = rawUpdateURL
    default:
      return nil
    }
    return NativeRecoveryVersionResponse(
      platform: expectedPlatform,
      latestVersion: latestVersion,
      latestBuild: latestBuild,
      minimumSupportedVersion: minimumSupportedVersion,
      minimumSupportedBuild: minimumSupportedBuild,
      updateState: updateState,
      updateURL: updateURL,
      recoveryURL: recoveryURL
    )
  }

  private static func nonBlankString(_ value: Any?) -> String? {
    guard let value = value as? String else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }

  private static func positiveDecimal(_ value: Any?) -> Int? {
    guard let raw = value as? String,
          raw.range(of: "^[1-9][0-9]*$", options: .regularExpression) != nil,
          let parsed = Int(raw),
          parsed > 0
    else {
      return nil
    }
    return parsed
  }
}
