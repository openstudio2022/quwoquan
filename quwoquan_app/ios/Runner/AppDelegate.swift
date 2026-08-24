import AVFoundation
import CoreFoundation
import CoreTelephony
import CoreGraphics
import CoreLocation
import CryptoKit
import EventKit
import Foundation
import Flutter
import Darwin
import MetricKit
import PushKit
import Security
import UIKit

/// 仅持久化已脱敏的原生未捕获异常类别，供下次 Dart 启动产出一条标准诊断事实。
/// 原生异常消息与堆栈绝不能写入 UserDefaults 或运行时日志管道。
private let nativeCrashMarkerKindKey = "qwq.runtime.previous_native_crash_kind"
private let startupHealthBuildKey = "qwq.runtime.startup_health_build"
private let startupHealthSafeShellKey = "qwq.runtime.startup_health_safe_shell"
private let startupHealthFatalBuildKey = "qwq.runtime.startup_health_fatal_build"
private let startupHealthFatalAtKey = "qwq.runtime.startup_health_fatal_at"
private let startupHealthFatalQueuedIdentityKey =
  "qwq.runtime.startup_health_fatal_queued_identity"
private var previousNativeCrashHandler: (@convention(c) (NSException) -> Void)?
private let nativeRuntimePackageFileName = "runtime-config-package.json"
private let nativeRuntimeTrustFileName = "runtime-config-trust.json"
private let nativeRuntimeActivationRequestFileName = "runtime-config-activation-request.json"
private let nativeRuntimeActivationReceiptFileName = "runtime-config-activation-receipt.json"
private let nativeRuntimeActiveReceiptFileName = "runtime-config-active-receipt.json"
private let nativeRuntimeActivationRequestDigestArgument =
  "--qwq-runtime-config-activation-request-digest"
private let nativeRuntimeConfigDirectory = "qwq_runtime"
private let nativeRuntimeConfigMaximumBytes = 1024 * 1024

private func persistNativeCrashMarker(_ exception: NSException) {
  let rawKind = exception.name.rawValue
  let normalized = rawKind
    .replacingOccurrences(
      of: "[^A-Za-z0-9_.-]",
      with: "_",
      options: .regularExpression
    )
  let kind = String(normalized.prefix(80))
  UserDefaults.standard.set(
    kind.isEmpty ? "UnknownNativeError" : kind,
    forKey: nativeCrashMarkerKindKey
  )
  if !UserDefaults.standard.bool(forKey: startupHealthSafeShellKey) {
    _ = NativeCrashMarkerStore.markFatalStartup()
  }
  // 仅尽力持久化，平台仍必须完全掌控终止流程。
  CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
  previousNativeCrashHandler?(exception)
}

private func nativeSHA256Identity(_ data: Data) -> String {
  "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private enum NativeCrashMarkerStore {
  private static var installed = false

  static func install() {
    guard !installed else { return }
    installed = true
    previousNativeCrashHandler = NSGetUncaughtExceptionHandler()
    NSSetUncaughtExceptionHandler(persistNativeCrashMarker)
  }

  static func consume() -> [String: String]? {
    guard !shouldRecoverCurrentBuild() else { return nil }
    guard let kind = UserDefaults.standard.string(forKey: nativeCrashMarkerKindKey),
          !kind.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return nil
    }
    UserDefaults.standard.removeObject(forKey: nativeCrashMarkerKindKey)
    return ["kind": kind]
  }

  static func pendingFatal() -> [String: String]? {
    guard shouldRecoverCurrentBuild(),
          let occurredAt = UserDefaults.standard.object(
            forKey: startupHealthFatalAtKey
          ) as? NSNumber
    else {
      return nil
    }
    let storedKind = UserDefaults.standard.string(forKey: nativeCrashMarkerKindKey) ?? ""
    let kind = storedKind.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      ? "NativeStartupCrash"
      : storedKind
    let date = Date(timeIntervalSince1970: occurredAt.doubleValue)
    return [
      "errorType": kind,
      "occurredAt": ISO8601DateFormatter().string(from: date),
    ]
  }

  static func acknowledgePendingFatal() {
    UserDefaults.standard.removeObject(forKey: nativeCrashMarkerKindKey)
  }

  static var currentBuild: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? ""
  }

  static var currentArtifactIdentity: String {
    switch NativeRuntimeConfigStore.readActivePackage() {
    case .present(let active):
      let package = active.package
      let environment = package["environment"] as? String ?? "unknown"
      let target = package["target"] as? String ?? "missing"
      let buildProfile = active.artifactTrustEnvelope["buildProfile"] as? String ?? "missing"
      return "\(currentBuild)|\(buildProfile)|\(environment)|\(target)|\(active.packageDigest)"
    case .absent(let trust):
      let buildProfile = trust.artifactTrustEnvelope["buildProfile"] as? String ?? "missing"
      return "\(currentBuild)|\(buildProfile)|runtime-config-absent|\(trust.trustEnvelopeDigest)"
    case .failure(let error):
      return "\(currentBuild)|runtime-config-failure|\(error.flutterCode)"
    }
  }

  static func shouldRecoverCurrentBuild() -> Bool {
    let fatalBuild = UserDefaults.standard.string(forKey: startupHealthFatalBuildKey) ?? ""
    guard !fatalBuild.isEmpty else { return false }
    guard fatalBuild == currentArtifactIdentity else {
      clearFatalMarker(reason: "artifact_mismatch")
      return false
    }
    let startupBuild = UserDefaults.standard.string(forKey: startupHealthBuildKey) ?? ""
    guard startupBuild == currentArtifactIdentity else {
      clearFatalMarker(reason: "artifact_mismatch")
      return false
    }
    guard !UserDefaults.standard.bool(forKey: startupHealthSafeShellKey) else {
      clearFatalMarker(reason: "safe_shell_conflict")
      return false
    }
    return true
  }

  static func markStarting() {
    UserDefaults.standard.set(currentArtifactIdentity, forKey: startupHealthBuildKey)
    UserDefaults.standard.set(false, forKey: startupHealthSafeShellKey)
    CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
  }

  @discardableResult
  static func markFatalStartup() -> Bool {
    let startupBuild = UserDefaults.standard.string(forKey: startupHealthBuildKey) ?? ""
    guard startupBuild == currentArtifactIdentity,
          !UserDefaults.standard.bool(forKey: startupHealthSafeShellKey)
    else {
      return false
    }
    UserDefaults.standard.set(currentArtifactIdentity, forKey: startupHealthFatalBuildKey)
    UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: startupHealthFatalAtKey)
    CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
    return true
  }

  static func markSafeShell() {
    UserDefaults.standard.set(currentArtifactIdentity, forKey: startupHealthBuildKey)
    UserDefaults.standard.set(true, forKey: startupHealthSafeShellKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalBuildKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalAtKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalQueuedIdentityKey)
  }

  #if QWQ_STARTUP_GATE_TEST_CONTROL
    static func seedConfirmedFatalForDebugTest() -> Bool {
      markStarting()
      return markFatalStartup()
    }

    static func clearFatalForDebugTest() {
      UserDefaults.standard.removeObject(forKey: startupHealthFatalBuildKey)
      UserDefaults.standard.removeObject(forKey: startupHealthFatalAtKey)
      UserDefaults.standard.removeObject(forKey: startupHealthFatalQueuedIdentityKey)
      CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
    }
  #endif

  static func fatalNeedsQueueing() -> Bool {
    guard shouldRecoverCurrentBuild() else { return false }
    let queuedIdentity = UserDefaults.standard.string(
      forKey: startupHealthFatalQueuedIdentityKey
    ) ?? ""
    return queuedIdentity != currentArtifactIdentity
  }

  static func markFatalQueued() {
    UserDefaults.standard.set(
      currentArtifactIdentity,
      forKey: startupHealthFatalQueuedIdentityKey
    )
    CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
  }

  static var effectiveLaunchManifestDigest: String {
    (try? NativeRuntimeConfigActivationCoordinator.readVerifiedIdentity()
      .effectiveLaunchManifestDigest) ?? ""
  }

  private static func clearFatalMarker(reason: String) {
    UserDefaults.standard.removeObject(forKey: startupHealthFatalBuildKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalAtKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalQueuedIdentityKey)
    CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
    NSLog("QWQStartup startup_fatal_marker_stale_cleared reason=%@", reason)
  }

}

enum NativeRuntimeConfigReadError: Error {
  case trustMissing
  case trustPathInvalid
  case trustTooLarge
  case trustMalformed
  case packageMissing
  case packagePathInvalid
  case packageTooLarge
  case packageMalformed
  case schemaMismatch
  case profileMismatch
  case targetMismatch
  case policyMismatch
  case algorithmMismatch
  case keyringMismatch
  case signatureKeyUntrusted
  case payloadDigestMismatch
  case packageDigestMismatch
  case trustDigestMismatch
  case signatureInvalid
  case freshnessInvalid
  case activeDigestConflict
  case activationWriteFailed
  case activationReadbackFailed
  case activationRollbackFailed
  case activationRequiresColdStart
  case activationRequestMissing
  case activationRequestMalformed
  case activationRequestDigestInvalid
  case activationRequestDigestMismatch
  case effectiveManifestMalformed
  case effectiveManifestDigestMismatch
  case activationIdentityMismatch
  case activationReceiptMissing
  case activationReceiptReadFailed
  case activationReceiptMalformed
  case activationReceiptMismatch
  case activationReceiptWriteFailed
  case internalFailure

  var flutterCode: String {
    switch self {
    case .trustMissing: return "runtime_config_trust_missing"
    case .trustPathInvalid: return "runtime_config_trust_path_invalid"
    case .trustTooLarge: return "runtime_config_trust_too_large"
    case .trustMalformed: return "runtime_config_trust_malformed"
    case .packageMissing: return "runtime_config_package_missing"
    case .packagePathInvalid: return "runtime_config_package_path_invalid"
    case .packageTooLarge: return "runtime_config_package_too_large"
    case .packageMalformed: return "runtime_config_package_malformed"
    case .schemaMismatch: return "runtime_config_schema_mismatch"
    case .profileMismatch: return "runtime_config_profile_mismatch"
    case .targetMismatch: return "runtime_config_target_mismatch"
    case .policyMismatch: return "runtime_config_launch_policy_mismatch"
    case .algorithmMismatch: return "runtime_config_signature_algorithm_mismatch"
    case .keyringMismatch: return "runtime_config_keyring_mismatch"
    case .signatureKeyUntrusted: return "runtime_config_signature_key_untrusted"
    case .payloadDigestMismatch: return "runtime_config_payload_digest_mismatch"
    case .packageDigestMismatch: return "runtime_config_package_digest_mismatch"
    case .trustDigestMismatch: return "runtime_config_trust_digest_mismatch"
    case .signatureInvalid: return "runtime_config_signature_invalid"
    case .freshnessInvalid: return "runtime_config_freshness_invalid"
    case .activeDigestConflict: return "runtime_config_active_digest_conflict"
    case .activationWriteFailed: return "runtime_config_activation_write_failed"
    case .activationReadbackFailed: return "runtime_config_activation_readback_failed"
    case .activationRollbackFailed: return "runtime_config_activation_rollback_failed"
    case .activationRequiresColdStart: return "runtime_config_activation_requires_cold_start"
    case .activationRequestMissing: return "runtime_config_activation_request_missing"
    case .activationRequestMalformed: return "runtime_config_activation_request_malformed"
    case .activationRequestDigestInvalid:
      return "runtime_config_activation_request_digest_invalid"
    case .activationRequestDigestMismatch:
      return "runtime_config_activation_request_digest_mismatch"
    case .effectiveManifestMalformed: return "runtime_config_effective_manifest_malformed"
    case .effectiveManifestDigestMismatch:
      return "runtime_config_effective_manifest_digest_mismatch"
    case .activationIdentityMismatch: return "runtime_config_activation_identity_mismatch"
    case .activationReceiptMissing: return "runtime_config_activation_receipt_missing"
    case .activationReceiptReadFailed:
      return "runtime_config_activation_receipt_read_failed"
    case .activationReceiptMalformed:
      return "runtime_config_activation_receipt_malformed"
    case .activationReceiptMismatch: return "runtime_config_activation_receipt_mismatch"
    case .activationReceiptWriteFailed:
      return "runtime_config_activation_receipt_write_failed"
    case .internalFailure: return "runtime_config_internal_failure"
    }
  }
}

private struct NativeRuntimeConfigTrustProjection {
  let artifactTrustEnvelope: [String: Any]
  let trustEnvelopeDigest: String
  let trustedPublicKeys: [String: String]
}

private struct NativeRuntimeConfigActiveProjection {
  let package: [String: Any]
  let artifactTrustEnvelope: [String: Any]
  let packageDigest: String
  let trustEnvelopeDigest: String

  var flutterEnvelope: [String: Any] {
    [
      "package": package,
      "trustedBuildProfile": artifactTrustEnvelope["buildProfile"] as? String ?? "",
      "trustedTarget": package["target"] as? String ?? "",
      "trustedPublicKeys": artifactTrustEnvelope["trustedPublicKeys"] as? [String: Any] ?? [:],
    ]
  }

  var readerEnvelope: [String: Any] {
    [
      "state": "present",
      "package": package,
      "artifactTrustEnvelope": artifactTrustEnvelope,
      "packageDigest": packageDigest,
      "trustEnvelopeDigest": trustEnvelopeDigest,
    ]
  }
}

private enum NativeRuntimeConfigReadState {
  case present(NativeRuntimeConfigActiveProjection)
  case absent(NativeRuntimeConfigTrustProjection)
  case failure(NativeRuntimeConfigReadError)
}

private struct NativeRuntimeConfigActivationResult {
  let packageDigest: String
  let trustEnvelopeDigest: String
  let previousActiveDigest: String
}

private enum NativeRuntimeConfigStore {
  private static let packageFields: Set<String> = [
    "schema", "environment", "buildProfile", "target",
    "launchPolicy", "issuedAt", "expiresAt", "sourceGitSha", "sourceTreeDigest",
    "runtime", "payloadDigest", "signatureAlgorithm", "signatureKeyId",
    "trustedPublicKeys", "signature",
  ]
  private static let runtimeFields: Set<String> = [
    "appRuntimeEnv", "gatewayBaseUrl", "legalBaseUrl", "publicWebBaseUrl",
    "appDownloadBaseUrl", "realtimeBaseUrl", "mediaAvatarCdnBaseUrl",
    "mediaImageCdnBaseUrl", "mediaVideoCdnBaseUrl", "mediaUploadBaseUrl",
    "rtcMediaConnectionUrl",
  ]
  private static let targetEnvironments = [
    "alpha-local": "alpha",
    "beta-local": "beta",
    "gamma-local": "gamma",
    "prod-sim": "prod",
    "prod-hosted": "prod",
  ]
  private static let maximumLifetime: TimeInterval = 86_400
  private static let maximumFutureSkew: TimeInterval = 300
  private static let writeQueue = DispatchQueue(label: "quwoquan.runtime.config.activation")

  static func readActivePackage() -> NativeRuntimeConfigReadState {
    loadActivePackage()
  }

  private static func loadActivePackage() -> NativeRuntimeConfigReadState {
    do {
      let trust = try loadTrustEnvelope()
      guard let packageURL = try runtimePackageURL(createDirectory: false) else {
        return .absent(trust)
      }
      let storedPackageData = try readData(
        url: packageURL,
        pathError: .packagePathInvalid,
        sizeError: .packageTooLarge,
        malformedError: .packageMalformed
      )
      let package = try decodeDocument(storedPackageData, malformedError: .packageMalformed)
      let canonicalPackageData = try canonicalJSONData(package)
      let active = try validatePackage(
        package,
        packageData: canonicalPackageData,
        trust: trust,
        expectedPackageDigest: nil
      )
      return .present(active)
    } catch let error as NativeRuntimeConfigReadError {
      return .failure(error)
    } catch {
      return .failure(.packageMalformed)
    }
  }

  static func readRuntimeConfig() throws -> [String: Any] {
    let identity = try NativeRuntimeConfigActivationCoordinator.readVerifiedIdentity()
    switch readActivePackage() {
    case .present(let active):
      var envelope = active.flutterEnvelope
      envelope["runtimeConfigPackageDigest"] = active.packageDigest
      envelope["runtimeConfigTrustEnvelopeDigest"] = active.trustEnvelopeDigest
      envelope["effectiveLaunchManifestDigest"] = identity.effectiveLaunchManifestDigest
      return envelope
    case .absent:
      throw NativeRuntimeConfigReadError.packageMissing
    case .failure(let error):
      throw error
    }
  }

  static func readRuntimeConfigState() -> [String: Any] {
    switch readActivePackage() {
    case .present(let active):
      return active.readerEnvelope
    case .absent(let trust):
      return [
        "state": "absent",
        "artifactTrustEnvelope": trust.artifactTrustEnvelope,
        "trustEnvelopeDigest": trust.trustEnvelopeDigest,
      ]
    case .failure(let error):
      return [
        "state": "failure",
        "errorCode": error.flutterCode,
      ]
    }
  }

  static func activate(
    package rawPackage: [String: Any],
    expectedPackageDigest: String,
    expectedTrustEnvelopeDigest: String,
    expectedActiveDigest: String,
    commit: ((NativeRuntimeConfigActivationResult) throws -> Void)? = nil
  ) throws -> NativeRuntimeConfigActivationResult {
    guard digestIdentity(expectedPackageDigest) != nil else {
      throw NativeRuntimeConfigReadError.packageDigestMismatch
    }
    guard digestIdentity(expectedTrustEnvelopeDigest) != nil else {
      throw NativeRuntimeConfigReadError.trustDigestMismatch
    }
    guard expectedActiveDigest.isEmpty || digestIdentity(expectedActiveDigest) != nil else {
      throw NativeRuntimeConfigReadError.activeDigestConflict
    }
    return try writeQueue.sync {
      let trust = try loadTrustEnvelope()
      guard trust.trustEnvelopeDigest == expectedTrustEnvelopeDigest else {
        throw NativeRuntimeConfigReadError.trustDigestMismatch
      }
      let currentState = loadActivePackage()
      let currentDigest: String
      switch currentState {
      case .present(let active):
        currentDigest = active.packageDigest
      case .absent:
        currentDigest = ""
      case .failure(let error):
        throw error
      }
      guard currentDigest == expectedActiveDigest else {
        throw NativeRuntimeConfigReadError.activeDigestConflict
      }
      let packageData = try canonicalJSONData(rawPackage)
      let validated = try validatePackage(
        rawPackage,
        packageData: packageData,
        trust: trust,
        expectedPackageDigest: expectedPackageDigest
      )
      let previousActivePackage = try readCurrentActivePackageData()
      do {
        try atomicallyActivate(packageData)
        let activatedState = loadActivePackage()
        guard case .present(let activated) = activatedState,
              activated.packageDigest == validated.packageDigest,
              activated.trustEnvelopeDigest == validated.trustEnvelopeDigest
        else {
          throw NativeRuntimeConfigReadError.activationReadbackFailed
        }
        let result = NativeRuntimeConfigActivationResult(
          packageDigest: validated.packageDigest,
          trustEnvelopeDigest: validated.trustEnvelopeDigest,
          previousActiveDigest: currentDigest
        )
        try commit?(result)
        return result
      } catch {
        try restorePreviousActivePackage(previousActivePackage, originalError: error)
        if let typed = error as? NativeRuntimeConfigReadError {
          throw typed
        }
        throw NativeRuntimeConfigReadError.activationReadbackFailed
      }
    }
  }

  private static func loadTrustEnvelope() throws -> NativeRuntimeConfigTrustProjection {
    guard let trustURL = bundledTrustURL() else {
      throw NativeRuntimeConfigReadError.trustMissing
    }
    let trustData = try readData(
      url: trustURL,
      pathError: .trustPathInvalid,
      sizeError: .trustTooLarge,
      malformedError: .trustMalformed
    )
    let trust = try decodeDocument(trustData, malformedError: .trustMalformed)
    guard Set(trust.keys) == [
      "schema", "buildProfile", "signatureAlgorithm", "trustedPublicKeys",
    ],
      trust["schema"] as? String == "app-runtime-config-trust",
      trust["signatureAlgorithm"] as? String == "ed25519",
      let buildProfile = nonEmptyString(trust["buildProfile"]),
      ["nonprod", "prod"].contains(buildProfile)
    else {
      throw NativeRuntimeConfigReadError.trustMalformed
    }
    let trustedPublicKeys = try normalizedKeyring(trust["trustedPublicKeys"])
    return NativeRuntimeConfigTrustProjection(
      artifactTrustEnvelope: trust,
      trustEnvelopeDigest: nativeSHA256Identity(try canonicalJSONData(trust)),
      trustedPublicKeys: trustedPublicKeys
    )
  }

  private static func validatePackage(
    _ package: [String: Any],
    packageData: Data,
    trust: NativeRuntimeConfigTrustProjection,
    expectedPackageDigest: String?
  ) throws -> NativeRuntimeConfigActiveProjection {
    guard Set(package.keys) == packageFields,
          package["schema"] as? String == "app-runtime-config-package"
    else {
      throw NativeRuntimeConfigReadError.schemaMismatch
    }
    guard package["signatureAlgorithm"] as? String == "ed25519",
          trust.artifactTrustEnvelope["signatureAlgorithm"] as? String == "ed25519"
    else {
      throw NativeRuntimeConfigReadError.algorithmMismatch
    }
    guard let profile = nonEmptyString(package["buildProfile"]),
          profile == trust.artifactTrustEnvelope["buildProfile"] as? String
    else {
      throw NativeRuntimeConfigReadError.profileMismatch
    }
    guard let environment = nonEmptyString(package["environment"]),
          let target = nonEmptyString(package["target"]),
          targetEnvironments[target] == environment
    else {
      throw NativeRuntimeConfigReadError.targetMismatch
    }
    let expectedPolicy = profile == "prod" ? "prod_release" : "test_live"
    let allowedEnvironments = profile == "prod"
      ? Set(["prod"])
      : Set(["alpha", "beta", "gamma"])
    guard allowedEnvironments.contains(environment),
          package["launchPolicy"] as? String == expectedPolicy
    else {
      throw NativeRuntimeConfigReadError.policyMismatch
    }
    guard let runtime = package["runtime"] as? [String: Any],
          Set(runtime.keys) == runtimeFields,
          runtime["appRuntimeEnv"] as? String == environment,
          runtime.values.allSatisfy({ nonEmptyString($0) != nil })
    else {
      throw NativeRuntimeConfigReadError.schemaMismatch
    }
    let packageKeyring = try normalizedKeyring(package["trustedPublicKeys"])
    guard packageKeyring == trust.trustedPublicKeys else {
      throw NativeRuntimeConfigReadError.keyringMismatch
    }
    guard let keyID = nonEmptyString(package["signatureKeyId"]),
          let encodedPublicKey = trust.trustedPublicKeys[keyID],
          let publicKeyData = Data(base64Encoded: encodedPublicKey),
          publicKeyData.count == 32
    else {
      throw NativeRuntimeConfigReadError.signatureKeyUntrusted
    }
    guard let encodedSignature = nonEmptyString(package["signature"]),
          let signature = Data(base64Encoded: encodedSignature),
          signature.count == 64,
          signature.base64EncodedString() == encodedSignature
    else {
      throw NativeRuntimeConfigReadError.signatureInvalid
    }
    guard let sourceGitSHA = nonEmptyString(package["sourceGitSha"]),
          sourceGitSHA.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil,
          let sourceTreeDigest = nonEmptyString(package["sourceTreeDigest"]),
          sourceTreeDigest.range(
            of: "^sha(?:1|256):[0-9a-f]+$",
            options: .regularExpression
          ) != nil
    else {
      throw NativeRuntimeConfigReadError.schemaMismatch
    }
    var payloadDigestDocument = package
    payloadDigestDocument.removeValue(forKey: "signature")
    payloadDigestDocument["payloadDigest"] = ""
    let computedPayloadDigest = nativeSHA256Identity(
      try canonicalJSONData(payloadDigestDocument)
    )
    guard package["payloadDigest"] as? String == computedPayloadDigest else {
      throw NativeRuntimeConfigReadError.payloadDigestMismatch
    }
    var signedPayload = package
    signedPayload.removeValue(forKey: "signature")
    let signedPayloadData = try canonicalJSONData(signedPayload)
    do {
      let publicKey = try Curve25519.Signing.PublicKey(rawRepresentation: publicKeyData)
      guard publicKey.isValidSignature(signature, for: signedPayloadData) else {
        throw NativeRuntimeConfigReadError.signatureInvalid
      }
    } catch let error as NativeRuntimeConfigReadError {
      throw error
    } catch {
      throw NativeRuntimeConfigReadError.signatureInvalid
    }
    try validateFreshness(package)
    let packageDigest = nativeSHA256Identity(try canonicalJSONData(package))
    if let expectedPackageDigest, packageDigest != expectedPackageDigest {
      throw NativeRuntimeConfigReadError.packageDigestMismatch
    }
    let canonicalPackageData = try canonicalJSONData(package)
    if packageData != canonicalPackageData {
      throw NativeRuntimeConfigReadError.packageMalformed
    }
    return NativeRuntimeConfigActiveProjection(
      package: package,
      artifactTrustEnvelope: trust.artifactTrustEnvelope,
      packageDigest: packageDigest,
      trustEnvelopeDigest: trust.trustEnvelopeDigest
    )
  }

  private static func validateFreshness(_ package: [String: Any]) throws {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let fallback = ISO8601DateFormatter()
    guard let issuedRaw = nonEmptyString(package["issuedAt"]),
          let expiresRaw = nonEmptyString(package["expiresAt"]),
          let issuedAt = formatter.date(from: issuedRaw) ?? fallback.date(from: issuedRaw),
          let expiresAt = formatter.date(from: expiresRaw) ?? fallback.date(from: expiresRaw),
          expiresAt > issuedAt,
          expiresAt.timeIntervalSince(issuedAt) <= maximumLifetime,
          issuedAt.timeIntervalSinceNow <= maximumFutureSkew,
          expiresAt > Date()
    else {
      throw NativeRuntimeConfigReadError.freshnessInvalid
    }
  }

  private static func normalizedKeyring(_ value: Any?) throws -> [String: String] {
    guard let rawKeyring = value as? [String: Any], !rawKeyring.isEmpty else {
      throw NativeRuntimeConfigReadError.keyringMismatch
    }
    var keyring: [String: String] = [:]
    let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
    for (keyID, rawValue) in rawKeyring {
      guard !keyID.isEmpty,
            keyID.count <= 128,
            keyID.unicodeScalars.allSatisfy({ allowed.contains($0) }),
            let encoded = nonEmptyString(rawValue),
            let decoded = Data(base64Encoded: encoded),
            decoded.count == 32,
            decoded.base64EncodedString() == encoded
      else {
        throw NativeRuntimeConfigReadError.keyringMismatch
      }
      keyring[keyID] = encoded
    }
    return keyring
  }

  private static func canonicalJSONData(_ document: [String: Any]) throws -> Data {
    guard JSONSerialization.isValidJSONObject(document) else {
      throw NativeRuntimeConfigReadError.packageMalformed
    }
    do {
      return try JSONSerialization.data(
        withJSONObject: document,
        options: [.sortedKeys, .withoutEscapingSlashes]
      )
    } catch {
      throw NativeRuntimeConfigReadError.packageMalformed
    }
  }

  private static func decodeDocument(
    _ data: Data,
    malformedError: NativeRuntimeConfigReadError
  ) throws -> [String: Any] {
    do {
      guard let document = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            !document.isEmpty
      else {
        throw malformedError
      }
      return document
    } catch let error as NativeRuntimeConfigReadError {
      throw error
    } catch {
      throw malformedError
    }
  }

  private static func readData(
    url: URL,
    pathError: NativeRuntimeConfigReadError,
    sizeError: NativeRuntimeConfigReadError,
    malformedError: NativeRuntimeConfigReadError
  ) throws -> Data {
    guard let values = try? url.resourceValues(forKeys: [
      .isRegularFileKey,
      .isSymbolicLinkKey,
      .fileSizeKey,
    ]),
      values.isRegularFile == true,
      values.isSymbolicLink != true
    else {
      throw pathError
    }
    guard let size = values.fileSize, size > 0, size <= nativeRuntimeConfigMaximumBytes else {
      throw sizeError
    }
    do {
      return try Data(contentsOf: url, options: [.mappedIfSafe])
    } catch {
      throw malformedError
    }
  }

  private static func readCurrentActivePackageData() throws -> Data? {
    guard let packageURL = try runtimePackageURL(createDirectory: false) else {
      return nil
    }
    return try readData(
      url: packageURL,
      pathError: .packagePathInvalid,
      sizeError: .packageTooLarge,
      malformedError: .packageMalformed
    )
  }

  private static func restorePreviousActivePackage(
    _ previousActivePackage: Data?,
    originalError: Error
  ) throws {
    do {
      let destination = try runtimePackageDestinationURL(createDirectory: true)
      if let previousActivePackage {
        try writeAndReplace(previousActivePackage, destination: destination)
      } else if FileManager.default.fileExists(atPath: destination.path) {
        try FileManager.default.removeItem(at: destination)
        try synchronizeDirectory(destination.deletingLastPathComponent())
      }
    } catch {
      let originalCode = (originalError as? NativeRuntimeConfigReadError)?.flutterCode
        ?? NativeRuntimeConfigReadError.internalFailure.flutterCode
      NSLog(
        "QWQStartup ios_runtime_config_activation_rollback_failed originalCode=%@",
        originalCode
      )
      throw NativeRuntimeConfigReadError.activationRollbackFailed
    }
  }

  private static func runtimePackageURL(createDirectory: Bool) throws -> URL? {
    let packageURL = try runtimePackageDestinationURL(createDirectory: createDirectory)
    return FileManager.default.fileExists(atPath: packageURL.path) ? packageURL : nil
  }

  private static func runtimePackageDestinationURL(createDirectory: Bool) throws -> URL {
    let fileManager = FileManager.default
    let supportRoot: URL
    do {
      supportRoot = try fileManager.url(
        for: .applicationSupportDirectory,
        in: .userDomainMask,
        appropriateFor: nil,
        create: createDirectory
      ).standardizedFileURL
    } catch {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    let directory = supportRoot
      .appendingPathComponent(nativeRuntimeConfigDirectory, isDirectory: true)
      .standardizedFileURL
    guard directory.path.hasPrefix(supportRoot.path + "/") else {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    if createDirectory {
      do {
        try fileManager.createDirectory(
          at: directory,
          withIntermediateDirectories: true,
          attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
        )
      } catch {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
    }
    let packageURL = directory
      .appendingPathComponent(nativeRuntimePackageFileName, isDirectory: false)
      .standardizedFileURL
    guard packageURL.path.hasPrefix(directory.path + "/") else {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    return packageURL
  }

  private static func atomicallyActivate(_ packageData: Data) throws {
    let destination = try runtimePackageDestinationURL(createDirectory: true)
    try writeAndReplace(packageData, destination: destination)
  }

  private static func writeAndReplace(_ data: Data, destination: URL) throws {
    let fileManager = FileManager.default
    let temporary = destination.deletingLastPathComponent().appendingPathComponent(
      ".runtime-config-package.\(UUID().uuidString).tmp",
      isDirectory: false
    )
    do {
      guard fileManager.createFile(
        atPath: temporary.path,
        contents: nil,
        attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
      ) else {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
      let handle = try FileHandle(forWritingTo: temporary)
      do {
        try handle.write(contentsOf: data)
        try handle.synchronize()
        try handle.close()
      } catch {
        try? handle.close()
        throw error
      }
      if fileManager.fileExists(atPath: destination.path) {
        _ = try fileManager.replaceItemAt(
          destination,
          withItemAt: temporary,
          backupItemName: nil,
          options: []
        )
      } else {
        try fileManager.moveItem(at: temporary, to: destination)
      }
      try synchronizeDirectory(destination.deletingLastPathComponent())
    } catch {
      try? fileManager.removeItem(at: temporary)
      if let typed = error as? NativeRuntimeConfigReadError {
        throw typed
      }
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
  }

  private static func synchronizeDirectory(_ directory: URL) throws {
    let directoryHandle = open(directory.path, O_RDONLY)
    guard directoryHandle >= 0 else {
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
    defer { _ = close(directoryHandle) }
    guard fsync(directoryHandle) == 0 else {
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
  }

  private static func bundledTrustURL() -> URL? {
    Bundle.main.url(
      forResource: nativeRuntimeTrustFileName,
      withExtension: nil,
      subdirectory: nativeRuntimeConfigDirectory
    )
  }

  private static func digestIdentity(_ value: Any?) -> String? {
    guard let digest = nonEmptyString(value),
          digest.range(
            of: "^sha256:[0-9a-f]{64}$",
            options: .regularExpression
          ) != nil
    else {
      return nil
    }
    return digest
  }

  private static func nonEmptyString(_ value: Any?) -> String? {
    guard let string = value as? String else { return nil }
    let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }
}

struct NativeRuntimeConfigActivationIdentity {
  let packageDigest: String
  let trustEnvelopeDigest: String
  let effectiveLaunchManifestDigest: String
}

// Recovery 面消费的 runtime context 三态投影：缺席（首装）与读取失败必须分流，
// 失败携带登记错误码，不得吞错折叠为空上下文。
enum NativeRuntimeRecoveryContext {
  case present([String: Any])
  case absent
  case failure(String)
}

struct NativeRuntimeConfigActivationConsumeResult {
  let requested: Bool
  let activated: Bool
  let errorCode: String
  let validationIssues: [String]
}

enum NativeRuntimeConfigActivationCoordinator {
  private static let requestFields: Set<String> = [
    "schema", "environment", "buildProfile", "target", "package",
    "packageDigest", "trustEnvelopeDigest", "effectiveLaunchManifest",
    "effectiveLaunchManifestDigest", "expectedActiveDigest",
  ]
  private static let effectiveManifestFields: Set<String> = [
    "schema", "environment", "buildProfile", "target", "entrypoint", "launchMode",
    "launchPolicy", "runtimeConfigPackageDigest", "runtimeConfigTrustEnvelopeDigest",
    "requiresLocalTransport", "transport",
  ]
  private static let transportFields: Set<String> = [
    "required", "reverseExpectedPorts", "reverseActualPorts", "reverseReceiptDigest",
    "consumerLeaseId",
  ]
  private static let receiptFields: Set<String> = [
    "schema", "status", "requestDigest", "environment", "buildProfile",
    "target", "packageDigest", "trustEnvelopeDigest", "effectiveLaunchManifestDigest",
    "previousActiveDigest", "activePackageDigest", "errorCode", "validationIssues",
  ]

  static func consumePendingActivationRequest(
    arguments: [String],
    coldStartAllowed: Bool
  ) -> NativeRuntimeConfigActivationConsumeResult {
    guard let markerIndex = arguments.firstIndex(
      of: nativeRuntimeActivationRequestDigestArgument
    ) else {
      return NativeRuntimeConfigActivationConsumeResult(
        requested: false,
        activated: false,
        errorCode: "",
        validationIssues: []
      )
    }
    let expectedRequestDigest = arguments.indices.contains(markerIndex + 1)
      ? arguments[markerIndex + 1]
      : ""
    var request: [String: Any]?
    var requestDigest = canonicalDigest(expectedRequestDigest) ?? String(
      repeating: "0",
      count: 64
    ).withSHA256Prefix
    var previousActiveDigest = ""
    do {
      guard coldStartAllowed else {
        throw NativeRuntimeConfigReadError.activationRequiresColdStart
      }
      guard let normalizedRequestDigest = canonicalDigest(expectedRequestDigest) else {
        throw NativeRuntimeConfigReadError.activationRequestDigestInvalid
      }
      previousActiveDigest = try currentActiveDigest()
      let requestURL = try runtimeConfigFileURL(
        name: nativeRuntimeActivationRequestFileName,
        createDirectory: false,
        requireExisting: true
      )
      let requestData = try readActivationData(requestURL)
      requestDigest = nativeSHA256Identity(try requestData.canonicalJSONObjectData())
      guard requestDigest == normalizedRequestDigest else {
        throw NativeRuntimeConfigReadError.activationRequestDigestMismatch
      }
      let decoded = try requestData.activationJSONObject()
      request = decoded
      try validateRequest(decoded)
      if try isAlreadyActivated(request: decoded, requestDigest: requestDigest) {
        try? FileManager.default.removeItem(at: requestURL)
        return NativeRuntimeConfigActivationConsumeResult(
          requested: true,
          activated: true,
          errorCode: "",
          validationIssues: []
        )
      }
      guard let package = decoded["package"] as? [String: Any],
            let packageDigest = decoded["packageDigest"] as? String,
            let trustDigest = decoded["trustEnvelopeDigest"] as? String,
            let expectedActiveDigest = decoded["expectedActiveDigest"] as? String
      else {
        throw NativeRuntimeConfigReadError.activationRequestMalformed
      }
      _ = try NativeRuntimeConfigStore.activate(
        package: package,
        expectedPackageDigest: packageDigest,
        expectedTrustEnvelopeDigest: trustDigest,
        expectedActiveDigest: expectedActiveDigest
      ) { result in
        let receipt = buildReceipt(
          request: decoded,
          requestDigest: requestDigest,
          status: "activated",
          previousActiveDigest: result.previousActiveDigest,
          activePackageDigest: result.packageDigest,
          errorCode: "",
          validationIssues: []
        )
        try commitActivationReceipts(receipt)
      }
      try? FileManager.default.removeItem(at: requestURL)
      return NativeRuntimeConfigActivationConsumeResult(
        requested: true,
        activated: true,
        errorCode: "",
        validationIssues: []
      )
    } catch {
      var errorCode = (error as? NativeRuntimeConfigReadError)?.flutterCode
        ?? NativeRuntimeConfigReadError.internalFailure.flutterCode
      var issues = [errorCode]
      // 读取失败时状态未知：保持最后已知 CAS 值并追加 rollback_failed，不得宣称空 active，
      // 也不得覆盖原始失败码；只有确认读取成功且与 CAS 前不一致才升级为 rollback_failed。
      var activeDigest = previousActiveDigest
      var activeDigestUnknown = false
      do {
        activeDigest = try currentActiveDigest()
      } catch {
        activeDigestUnknown = true
      }
      let rollbackCode = NativeRuntimeConfigReadError.activationRollbackFailed.flutterCode
      if activeDigestUnknown {
        if !issues.contains(rollbackCode) {
          issues.append(rollbackCode)
        }
      } else if activeDigest != previousActiveDigest {
        errorCode = rollbackCode
        issues.insert(errorCode, at: 0)
      }
      if let request {
        do {
          let receipt = buildReceipt(
            request: request,
            requestDigest: requestDigest,
            status: "failed",
            previousActiveDigest: previousActiveDigest,
            activePackageDigest: activeDigest,
            errorCode: errorCode,
            validationIssues: issues
          )
          try writeReceipt(receipt, name: nativeRuntimeActivationReceiptFileName)
          let requestURL = try runtimeConfigFileURL(
            name: nativeRuntimeActivationRequestFileName,
            createDirectory: false,
            requireExisting: false
          )
          try? FileManager.default.removeItem(at: requestURL)
        } catch {
          if !issues.contains(NativeRuntimeConfigReadError.activationReceiptWriteFailed.flutterCode) {
            issues.append(NativeRuntimeConfigReadError.activationReceiptWriteFailed.flutterCode)
          }
        }
      }
      return NativeRuntimeConfigActivationConsumeResult(
        requested: true,
        activated: false,
        errorCode: errorCode,
        validationIssues: issues
      )
    }
  }

  // Active receipt 的缺席、读取失败与解码失败必须使用 receipt 语义错误码，
  // 不得复用 activation request 错误语义（metadata receipt 契约约束）。
  static func readActiveReceiptDocument() throws -> [String: Any] {
    let receiptURL = try runtimeConfigFileURL(
      name: nativeRuntimeActiveReceiptFileName,
      createDirectory: false,
      requireExisting: true,
      missingError: .activationReceiptMissing
    )
    let data = try readActivationData(
      receiptURL,
      malformedError: .activationReceiptMalformed,
      readFailedError: .activationReceiptReadFailed
    )
    return try data.activationJSONObject(malformedError: .activationReceiptMalformed)
  }

  static func readRecoveryRuntimeContext() -> NativeRuntimeRecoveryContext {
    let active: NativeRuntimeConfigActiveProjection
    switch NativeRuntimeConfigStore.readActivePackage() {
    case .absent:
      return .absent
    case .failure(let error):
      return .failure(error.flutterCode)
    case .present(let projection):
      active = projection
    }
    do {
      let identity = try readVerifiedIdentity()
      let runtime = active.package["runtime"] as? [String: Any] ?? [:]
      return .present([
        "runtimeEnvironment": active.package["environment"] as? String ?? "",
        "runtimeConfigDigest": identity.packageDigest,
        "effectiveLaunchManifestDigest": identity.effectiveLaunchManifestDigest,
        "recoveryBaseURL": runtime["gatewayBaseUrl"] as? String ?? "",
        "publicWebURL": runtime["publicWebBaseUrl"] as? String ?? "",
        "appDownloadBaseURL": runtime["appDownloadBaseUrl"] as? String ?? "",
      ])
    } catch {
      let code = (error as? NativeRuntimeConfigReadError)?.flutterCode
        ?? NativeRuntimeConfigReadError.internalFailure.flutterCode
      return .failure(code)
    }
  }

  static func readVerifiedIdentity() throws -> NativeRuntimeConfigActivationIdentity {
    let active: NativeRuntimeConfigActiveProjection
    switch NativeRuntimeConfigStore.readActivePackage() {
    case .present(let projection):
      active = projection
    case .absent:
      throw NativeRuntimeConfigReadError.packageMissing
    case .failure(let error):
      throw error
    }
    let receipt = try readActiveReceiptDocument()
    guard Set(receipt.keys) == receiptFields,
          receipt["schema"] as? String == "app-runtime-config-activation-receipt",
          receipt["status"] as? String == "activated",
          receipt["errorCode"] as? String == "",
          let issues = receipt["validationIssues"] as? [Any],
          issues.isEmpty,
          receipt["environment"] as? String == active.package["environment"] as? String,
          receipt["buildProfile"] as? String == active.package["buildProfile"] as? String,
          receipt["target"] as? String == active.package["target"] as? String,
          receipt["packageDigest"] as? String == active.packageDigest,
          receipt["activePackageDigest"] as? String == active.packageDigest,
          receipt["trustEnvelopeDigest"] as? String == active.trustEnvelopeDigest,
          canonicalDigest(receipt["requestDigest"] as? String) != nil,
          let manifestDigest = canonicalDigest(
            receipt["effectiveLaunchManifestDigest"] as? String
          )
    else {
      throw NativeRuntimeConfigReadError.activationReceiptMismatch
    }
    return NativeRuntimeConfigActivationIdentity(
      packageDigest: active.packageDigest,
      trustEnvelopeDigest: active.trustEnvelopeDigest,
      effectiveLaunchManifestDigest: manifestDigest
    )
  }

  private static func validateRequest(_ request: [String: Any]) throws {
    guard Set(request.keys) == requestFields,
          request["schema"] as? String == "app-runtime-config-activation-request",
          let environment = nonEmptyString(request["environment"]),
          let buildProfile = nonEmptyString(request["buildProfile"]),
          let target = nonEmptyString(request["target"]),
          let packageDigest = canonicalDigest(request["packageDigest"] as? String),
          let trustDigest = canonicalDigest(request["trustEnvelopeDigest"] as? String),
          let manifestDigest = canonicalDigest(
            request["effectiveLaunchManifestDigest"] as? String
          ),
          let expectedActiveDigest = request["expectedActiveDigest"] as? String,
          expectedActiveDigest.isEmpty || canonicalDigest(expectedActiveDigest) != nil,
          let package = request["package"] as? [String: Any],
          let manifest = request["effectiveLaunchManifest"] as? [String: Any]
    else {
      throw NativeRuntimeConfigReadError.activationRequestMalformed
    }
    guard Set(manifest.keys) == effectiveManifestFields,
          manifest["schema"] as? String == "app-effective-launch-manifest",
          manifest["entrypoint"] as? String == "lib/main_prod.dart",
          let transport = manifest["transport"] as? [String: Any],
          Set(transport.keys) == transportFields
    else {
      throw NativeRuntimeConfigReadError.effectiveManifestMalformed
    }
    guard nativeSHA256Identity(try canonicalJSONData(manifest)) == manifestDigest else {
      throw NativeRuntimeConfigReadError.effectiveManifestDigestMismatch
    }
    guard package["environment"] as? String == environment,
          package["buildProfile"] as? String == buildProfile,
          package["target"] as? String == target,
          package["launchPolicy"] as? String == manifest["launchPolicy"] as? String,
          manifest["environment"] as? String == environment,
          manifest["buildProfile"] as? String == buildProfile,
          manifest["target"] as? String == target,
          manifest["runtimeConfigPackageDigest"] as? String == packageDigest,
          manifest["runtimeConfigTrustEnvelopeDigest"] as? String == trustDigest
    else {
      throw NativeRuntimeConfigReadError.activationIdentityMismatch
    }
  }

  private static func buildReceipt(
    request: [String: Any],
    requestDigest: String,
    status: String,
    previousActiveDigest: String,
    activePackageDigest: String,
    errorCode: String,
    validationIssues: [String]
  ) -> [String: Any] {
    [
      "schema": "app-runtime-config-activation-receipt",
      "status": status,
      "requestDigest": requestDigest,
      "environment": request["environment"] as? String ?? "",
      "buildProfile": request["buildProfile"] as? String ?? "",
      "target": request["target"] as? String ?? "",
      "packageDigest": request["packageDigest"] as? String ?? "",
      "trustEnvelopeDigest": request["trustEnvelopeDigest"] as? String ?? "",
      "effectiveLaunchManifestDigest": request["effectiveLaunchManifestDigest"] as? String ?? "",
      "previousActiveDigest": previousActiveDigest,
      "activePackageDigest": activePackageDigest,
      "errorCode": errorCode,
      "validationIssues": validationIssues,
    ]
  }

  private static func commitActivationReceipts(_ receipt: [String: Any]) throws {
    try commitActivationReceipts(
      receipt,
      readExisting: { name in
        try readExistingActivationData(name: name)
      },
      write: { receipt, name in
        try writeReceipt(receipt, name: name)
      },
      restore: { data, name in
        try restoreExistingActivationData(data, name: name)
      }
    )
  }

  static func commitActivationReceipts(
    _ receipt: [String: Any],
    readExisting: (String) throws -> Data?,
    write: ([String: Any], String) throws -> Void,
    restore: (Data?, String) throws -> Void
  ) throws {
    let previousActiveReceipt = try readExisting(nativeRuntimeActiveReceiptFileName)
    let previousLaunchReceipt = try readExisting(nativeRuntimeActivationReceiptFileName)
    do {
      try write(receipt, nativeRuntimeActiveReceiptFileName)
      try write(receipt, nativeRuntimeActivationReceiptFileName)
    } catch {
      do {
        try restore(previousActiveReceipt, nativeRuntimeActiveReceiptFileName)
        try restore(previousLaunchReceipt, nativeRuntimeActivationReceiptFileName)
      } catch {
        throw NativeRuntimeConfigReadError.activationRollbackFailed
      }
      throw error
    }
  }

  private static func readExistingActivationData(name: String) throws -> Data? {
    let url = try runtimeConfigFileURL(
      name: name,
      createDirectory: true,
      requireExisting: false
    )
    guard FileManager.default.fileExists(atPath: url.path) else {
      return nil
    }
    do {
      return try Data(contentsOf: url, options: [.mappedIfSafe])
    } catch {
      throw NativeRuntimeConfigReadError.activationReceiptWriteFailed
    }
  }

  private static func restoreExistingActivationData(_ data: Data?, name: String) throws {
    let url = try runtimeConfigFileURL(
      name: name,
      createDirectory: true,
      requireExisting: false
    )
    if let data {
      try writeActivationData(data, destination: url)
    } else if FileManager.default.fileExists(atPath: url.path) {
      do {
        try FileManager.default.removeItem(at: url)
      } catch {
        throw NativeRuntimeConfigReadError.activationRollbackFailed
      }
    }
  }

  private static func writeReceipt(_ receipt: [String: Any], name: String) throws {
    let destination = try runtimeConfigFileURL(
      name: name,
      createDirectory: true,
      requireExisting: false
    )
    do {
      try writeActivationData(try canonicalJSONData(receipt), destination: destination)
    } catch {
      throw NativeRuntimeConfigReadError.activationReceiptWriteFailed
    }
  }

  private static func runtimeConfigFileURL(
    name: String,
    createDirectory: Bool,
    requireExisting: Bool,
    missingError: NativeRuntimeConfigReadError = .activationRequestMissing
  ) throws -> URL {
    let fileManager = FileManager.default
    let supportRoot: URL
    do {
      supportRoot = try fileManager.url(
        for: .applicationSupportDirectory,
        in: .userDomainMask,
        appropriateFor: nil,
        create: createDirectory
      ).standardizedFileURL
    } catch {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    let directory = supportRoot
      .appendingPathComponent(nativeRuntimeConfigDirectory, isDirectory: true)
      .standardizedFileURL
    guard directory.path.hasPrefix(supportRoot.path + "/") else {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    if createDirectory {
      do {
        try fileManager.createDirectory(
          at: directory,
          withIntermediateDirectories: true,
          attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
        )
      } catch {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
    }
    let candidate = directory.appendingPathComponent(name, isDirectory: false)
      .standardizedFileURL
    guard candidate.path.hasPrefix(directory.path + "/") else {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    if requireExisting && !fileManager.fileExists(atPath: candidate.path) {
      throw missingError
    }
    return candidate
  }

  private static func readActivationData(
    _ url: URL,
    malformedError: NativeRuntimeConfigReadError = .activationRequestMalformed,
    readFailedError: NativeRuntimeConfigReadError = .activationRequestMalformed
  ) throws -> Data {
    guard let values = try? url.resourceValues(forKeys: [
      .isRegularFileKey,
      .isSymbolicLinkKey,
      .fileSizeKey,
    ]),
      values.isRegularFile == true,
      values.isSymbolicLink != true,
      let size = values.fileSize,
      size > 0,
      size <= nativeRuntimeConfigMaximumBytes
    else {
      throw malformedError
    }
    do {
      return try Data(contentsOf: url, options: [.mappedIfSafe])
    } catch {
      throw readFailedError
    }
  }

  private static func writeActivationData(_ data: Data, destination: URL) throws {
    let temporary = destination.deletingLastPathComponent().appendingPathComponent(
      ".runtime-config-activation.\(UUID().uuidString).tmp",
      isDirectory: false
    )
    do {
      try data.write(
        to: temporary,
        options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication]
      )
      if FileManager.default.fileExists(atPath: destination.path) {
        _ = try FileManager.default.replaceItemAt(destination, withItemAt: temporary)
      } else {
        try FileManager.default.moveItem(at: temporary, to: destination)
      }
    } catch {
      try? FileManager.default.removeItem(at: temporary)
      throw NativeRuntimeConfigReadError.activationReceiptWriteFailed
    }
  }

  private static func currentActiveDigest() throws -> String {
    switch NativeRuntimeConfigStore.readActivePackage() {
    case .present(let active):
      return active.packageDigest
    case .absent:
      return ""
    case .failure(let error):
      throw error
    }
  }

  private static func isAlreadyActivated(
    request: [String: Any],
    requestDigest: String
  ) throws -> Bool {
    guard let expectedPackageDigest = request["packageDigest"] as? String,
          let expectedTrustDigest = request["trustEnvelopeDigest"] as? String,
          let expectedManifestDigest = request["effectiveLaunchManifestDigest"] as? String
    else {
      return false
    }
    let identity: NativeRuntimeConfigActivationIdentity
    do {
      identity = try readVerifiedIdentity()
    } catch NativeRuntimeConfigReadError.packageMissing,
            NativeRuntimeConfigReadError.activationReceiptMissing {
      return false
    }
    let receipt = try readActiveReceiptDocument()
    return receipt["requestDigest"] as? String == requestDigest
      && identity.packageDigest == expectedPackageDigest
      && identity.trustEnvelopeDigest == expectedTrustDigest
      && identity.effectiveLaunchManifestDigest == expectedManifestDigest
  }

  private static func canonicalJSONData(_ document: [String: Any]) throws -> Data {
    guard JSONSerialization.isValidJSONObject(document) else {
      throw NativeRuntimeConfigReadError.activationRequestMalformed
    }
    do {
      return try JSONSerialization.data(
        withJSONObject: document,
        options: [.sortedKeys, .withoutEscapingSlashes]
      )
    } catch {
      throw NativeRuntimeConfigReadError.activationRequestMalformed
    }
  }

  private static func canonicalDigest(_ value: String?) -> String? {
    guard let value,
          value.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil
    else {
      return nil
    }
    return value
  }

  private static func nonEmptyString(_ value: Any?) -> String? {
    guard let value = value as? String else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    return normalized.isEmpty ? nil : normalized
  }
}

private extension Data {
  func activationJSONObject(
    malformedError: NativeRuntimeConfigReadError = .activationRequestMalformed
  ) throws -> [String: Any] {
    do {
      guard let document = try JSONSerialization.jsonObject(with: self) as? [String: Any],
            !document.isEmpty
      else {
        throw malformedError
      }
      return document
    } catch let error as NativeRuntimeConfigReadError {
      throw error
    } catch {
      throw malformedError
    }
  }

  func canonicalJSONObjectData() throws -> Data {
    let document = try activationJSONObject()
    guard JSONSerialization.isValidJSONObject(document) else {
      throw NativeRuntimeConfigReadError.activationRequestMalformed
    }
    return try JSONSerialization.data(
      withJSONObject: document,
      options: [.sortedKeys, .withoutEscapingSlashes]
    )
  }
}

private extension String {
  var withSHA256Prefix: String { "sha256:" + self }
}

private final class RecoveryActionButton: UIButton {
  var recoveryAction: (() -> Void)?

  override init(frame: CGRect) {
    super.init(frame: frame)
    addTarget(self, action: #selector(invokeRecoveryAction), for: .touchUpInside)
  }

  required init?(coder: NSCoder) {
    super.init(coder: coder)
    addTarget(self, action: #selector(invokeRecoveryAction), for: .touchUpInside)
  }

  @objc private func invokeRecoveryAction() {
    recoveryAction?()
  }
}

@available(iOS 14.0, *)
private final class NativeHangMetricStore: NSObject, MXMetricManagerSubscriber {
  static let shared = NativeHangMetricStore()

  private static let occurredAtKey = "qwq.runtime.previous_native_hang_occurred_at"
  private static let durationMsKey = "qwq.runtime.previous_native_hang_duration_ms"
  private var installed = false

  func install() {
    guard !installed else { return }
    installed = true
    MXMetricManager.shared.add(self)
  }

  func didReceive(_ payloads: [MXMetricPayload]) {
    // 聚合 responsiveness histogram 不等同单次 hang；单次事实只消费 diagnostics。
  }

  func didReceive(_ payloads: [MXDiagnosticPayload]) {
    var latestOccurredAt: Date?
    var longestDurationMs: Int64 = 0
    for payload in payloads {
      guard let diagnostics = payload.hangDiagnostics,
            !diagnostics.isEmpty
      else {
        continue
      }
      if let currentLatest = latestOccurredAt {
        if payload.timeStampEnd > currentLatest {
          latestOccurredAt = payload.timeStampEnd
        }
      } else {
        latestOccurredAt = payload.timeStampEnd
      }
      for diagnostic in diagnostics {
        let durationMs = diagnostic.hangDuration
          .converted(to: UnitDuration.milliseconds)
          .value
        longestDurationMs = max(
          longestDurationMs,
          Int64(max(0, durationMs).rounded())
        )
      }
    }
    guard let latestOccurredAt else { return }
    UserDefaults.standard.set(
      Int64(latestOccurredAt.timeIntervalSince1970 * 1000),
      forKey: Self.occurredAtKey
    )
    if longestDurationMs > 0 {
      UserDefaults.standard.set(
        longestDurationMs,
        forKey: Self.durationMsKey
      )
    }
  }

  func read() -> [String: Any]? {
    let occurredAtEpochMs = UserDefaults.standard.object(
      forKey: Self.occurredAtKey
    ) as? NSNumber
    guard let occurredAtEpochMs, occurredAtEpochMs.int64Value > 0 else {
      return nil
    }
    let durationMs = UserDefaults.standard.object(
      forKey: Self.durationMsKey
    ) as? NSNumber
    var marker: [String: Any] = [
      "source": "ios_metric_kit",
      "occurredAtEpochMs": occurredAtEpochMs.int64Value,
    ]
    if let durationMs, durationMs.int64Value > 0 {
      marker["durationMs"] = durationMs.int64Value
    }
    return marker
  }

  func acknowledge(occurredAtEpochMs: Int64) -> Bool {
    let stored = UserDefaults.standard.object(
      forKey: Self.occurredAtKey
    ) as? NSNumber
    guard let stored else {
      return true
    }
    guard stored.int64Value == occurredAtEpochMs else {
      // 新诊断已覆盖旧标记时不得由旧 ACK 删除。
      return false
    }
    UserDefaults.standard.removeObject(forKey: Self.occurredAtKey)
    UserDefaults.standard.removeObject(forKey: Self.durationMsKey)
    return true
  }
}

/// 清理旧版启动 journal 的兼容壳。恢复规格不再生成 attemptId/checkpoint。
private final class StartupNativeTelemetryJournal {
  private static let eventsKey = "startup_telemetry_native_journal"
  private static let attemptKey = "startup_telemetry_native_attempt"

  private let defaults: UserDefaults

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    defaults.removeObject(forKey: Self.attemptKey)
    defaults.removeObject(forKey: Self.eventsKey)
  }

  func beginAttempt() {
    defaults.removeObject(forKey: Self.attemptKey)
    defaults.removeObject(forKey: Self.eventsKey)
  }

  func record(
    phase: String,
    elapsedMs: Int,
    outcome: String,
    failureCode: String = "",
    failureSource: String = "",
    deadlineOrigin: String = "ios_process"
  ) {
    // Intentionally empty.
  }

  var currentAttemptId: String { "" }

  func events() -> [String] {
    []
  }

  func clearEvents() {
    defaults.removeObject(forKey: Self.eventsKey)
    defaults.removeObject(forKey: Self.attemptKey)
  }
}

/// Keychain-backed AES key plus a protected file keeps the queue available before
/// Flutter plugins and the business container are initialized.
private final class RecoveryFailureEncryptedStore {
  // Existing Keychain account and file name are frozen canonical bytes.
  private static let keyAccount = "recovery-failure-queue-key-v1"
  private static let maximumEncryptedBytes = 2 << 20
  private let keychain = IncomingCallKeychainStore(
    service: "\(Bundle.main.bundleIdentifier ?? "com.quwoquan.app").recovery-failure"
  )

  func read() -> String? {
    let file = queueFile
    guard let encrypted = try? Data(contentsOf: file),
          !encrypted.isEmpty,
          encrypted.count <= Self.maximumEncryptedBytes,
          let keyData = keychain.data(forKey: Self.keyAccount),
          let box = try? AES.GCM.SealedBox(combined: encrypted),
          let plaintext = try? AES.GCM.open(box, using: SymmetricKey(data: keyData)),
          let value = String(data: plaintext, encoding: .utf8)
    else {
      clear()
      return nil
    }
    return value
  }

  func write(_ value: String) -> Bool {
    guard let plaintext = value.data(using: .utf8),
          !plaintext.isEmpty,
          plaintext.count <= Self.maximumEncryptedBytes,
          let key = encryptionKey(),
          let sealed = try? AES.GCM.seal(plaintext, using: key),
          let combined = sealed.combined,
          combined.count <= Self.maximumEncryptedBytes
    else { return false }
    do {
      try FileManager.default.createDirectory(
        at: queueFile.deletingLastPathComponent(),
        withIntermediateDirectories: true
      )
      try combined.write(to: queueFile, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
      return true
    } catch {
      return false
    }
  }

  @discardableResult
  func clear() -> Bool {
    guard FileManager.default.fileExists(atPath: queueFile.path) else { return true }
    do {
      try FileManager.default.removeItem(at: queueFile)
      return true
    } catch {
      return false
    }
  }

  private var queueFile: URL {
    let base = FileManager.default.urls(
      for: .applicationSupportDirectory,
      in: .userDomainMask
    ).first ?? FileManager.default.temporaryDirectory
    return base.appendingPathComponent("recovery_failures.v1.aesgcm", isDirectory: false)
  }

  private func encryptionKey() -> SymmetricKey? {
    if let existing = keychain.data(forKey: Self.keyAccount), existing.count == 32 {
      return SymmetricKey(data: existing)
    }
    var bytes = [UInt8](repeating: 0, count: 32)
    let status = bytes.withUnsafeMutableBytes { buffer in
      SecRandomCopyBytes(kSecRandomDefault, buffer.count, buffer.baseAddress!)
    }
    guard status == errSecSuccess else {
      return nil
    }
    let data = Data(bytes)
    guard keychain.set(data, forKey: Self.keyAccount) else { return nil }
    return SymmetricKey(data: data)
  }
}

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  // 所有构建都使用同一进程钟硬门；Debug 慢启动必须修关键路径，不能形成双时钟。
  private static let flutterFirstFrameDeadline: TimeInterval = 6
  private static let maximumRecoveryRecords = 20
  private static let maximumRecoveryRecordBytes = 64 << 10
  private static let recoveryRetention: TimeInterval = 7 * 24 * 60 * 60
  private let processStartUptime = ProcessInfo.processInfo.systemUptime
  private let videoEditingPlugin = VideoEditingPlugin()
  private let personalAssistantNativeApiPlugin = PersonalAssistantNativeApiPlugin()
  private let assistantDeviceActionPlugin = AssistantDeviceActionPlugin()
  private let commercialAuthPlugin = CommercialAuthPlugin()
  private let aliyunOneTapPlugin = AliyunOneTapPlugin()
  let incomingCallPushCoordinator = IncomingCallPushCoordinator()
  private let cellularNetworkInfo = CTTelephonyNetworkInfo()
  private let startupTelemetryJournal = StartupNativeTelemetryJournal()
  private let recoveryFailureEncryptedStore = RecoveryFailureEncryptedStore()
  private var flutterFirstFrameWatchdog: DispatchWorkItem?
  private var nativeRecoveryTerminalReconciliation: DispatchWorkItem?
  private var flutterFirstFrameConfirmed = false
  private var startupSafeTerminalConfirmed = false
  private var appInForeground = false
  private var nativeRecoveryShown = false
  private var nativeRecoveryDeadlineReached = false
  private var confirmedPreviousBuildFatal = false
  private var nativeActivationOnly = false
  private var nativeActivationFailureCode = ""
  private var nativeActivationValidationIssues: [String] = []
  private var recoveryExternalOpenInFlight = false
  private var recoveryExternalReturnPending = false
  private var recoveryVersionCheckInFlight = false
  private var recoveryVersionRefreshPending = false
  private var dartStartupAttemptStarted = false
  private var currentDartAttemptIsHotRestart = false
  private var currentDartAttemptId = ""
  private var currentLaunchMode = "unknown"
  private var currentDartAttemptStartedUptime: TimeInterval = 0
  private var firstFrameForegroundRemaining = AppDelegate.flutterFirstFrameDeadline
  private var foregroundStartedUptime: TimeInterval = 0
  private weak var startupRecoveryView: UIView?
  private weak var startupRecoveryTitle: UILabel?
  private weak var startupRecoveryMessage: UILabel?
  private weak var startupRecoveryPrimary: RecoveryActionButton?
  private weak var startupRecoveryWeb: RecoveryActionButton?

  override func application(
    _ application: UIApplication,
    willFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    NativeCrashMarkerStore.install()
    #if QWQ_STARTUP_GATE_TEST_CONTROL
      if ProcessInfo.processInfo.arguments.contains("--qwq-test-confirmed-startup-fatal") {
        if NativeCrashMarkerStore.seedConfirmedFatalForDebugTest() {
          NSLog("QWQStartup ios_debug_confirmed_startup_fatal_seeded")
        }
      } else if ProcessInfo.processInfo.arguments.contains("--qwq-test-clear-startup-fatal") {
        NativeCrashMarkerStore.clearFatalForDebugTest()
        NSLog("QWQStartup ios_debug_confirmed_startup_fatal_cleared")
      }
    #endif
    let activation = consumePendingActivationRequest()
    if activation.requested && !activation.activated {
      nativeActivationFailureCode = activation.errorCode
      nativeActivationValidationIssues = activation.validationIssues
      NSLog(
        "QWQStartup ios_runtime_config_activation_failed code=%@ issues=%@",
        nativeActivationFailureCode,
        nativeActivationValidationIssues.joined(separator: ",")
      )
      return true
    }
    if activation.activated {
      nativeActivationOnly = true
      NSLog("QWQStartup ios_runtime_config_activation_complete")
      // Canonical executor 验证回执后会用无 activation argument 的第二次冷启动
      // 进入 Flutter；当前进程只提交原生 CAS，绝不能创建 implicit engine。
      return true
    }
    confirmedPreviousBuildFatal = NativeCrashMarkerStore.shouldRecoverCurrentBuild()
    if confirmedPreviousBuildFatal {
      // FlutterAppDelegate 的 will/didFinish 都不得进入；恢复 gate 必须先于
      // implicit Flutter engine 与任何插件装配。
      return true
    }
    return super.application(
      application,
      willFinishLaunchingWithOptions: launchOptions
    )
  }

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    if nativeActivationOnly {
      startupSafeTerminalConfirmed = true
      NSLog("QWQStartup ios_native_activation_only_complete")
      return true
    }
    if !nativeActivationFailureCode.isEmpty {
      startupSafeTerminalConfirmed = true
      appInForeground = true
      NSLog(
        "QWQStartup ios_native_activation_gate_recovery code=%@",
        nativeActivationFailureCode
      )
      return true
    }
    if confirmedPreviousBuildFatal {
      startupSafeTerminalConfirmed = true
      appInForeground = true
      if !enqueueConfirmedStartupFatal() {
        NSLog("QWQStartup ios_native_startup_failure_queue_write_failed")
      }
      NSLog("QWQStartup ios_native_startup_gate_recovery")
      return true
    }
    NativeCrashMarkerStore.markStarting()
    if #available(iOS 14.0, *) {
      NativeHangMetricStore.shared.install()
    }
    NSLog("QWQStartup ios_did_finish_launching")
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    window?.backgroundColor = StartupTransitionBackground.color
    startupTelemetryJournal.record(
      phase: "native_pre_flutter",
      elapsedMs: Int((ProcessInfo.processInfo.systemUptime - processStartUptime) * 1000),
      outcome: "observed"
    )
    appInForeground = true
    currentDartAttemptStartedUptime = processStartUptime
    // 预算从进程最早可得的 monotonic 时钟开始，不能在 becomeActive 时重新给完整 6 秒。
    foregroundStartedUptime = processStartUptime
    armFlutterFirstFrameWatchdog()
    return launched
  }

  override func application(
    _ application: UIApplication,
    configurationForConnecting connectingSceneSession: UISceneSession,
    options: UIScene.ConnectionOptions
  ) -> UISceneConfiguration {
    guard confirmedPreviousBuildFatal
            || nativeActivationOnly
            || !nativeActivationFailureCode.isEmpty
    else {
      // FlutterAppDelegate adopts UIApplicationDelegate but does not implement
      // this optional selector on every engine version. Calling super here
      // therefore crashes normal launch with an unrecognized selector.
      let normal = UISceneConfiguration(
        name: "flutter",
        sessionRole: connectingSceneSession.role
      )
      normal.sceneClass = UIWindowScene.self
      normal.delegateClass = AppSceneDelegate.self
      normal.storyboard = UIStoryboard(name: "Main", bundle: nil)
      return normal
    }
    // Main.storyboard contains FlutterViewController. The fatal path must
    // replace the scene configuration before UIKit resolves that storyboard;
    // hiding the Flutter view later would already have created the implicit
    // engine behind the native recovery gate.
    let recovery = UISceneConfiguration(
      name: "native-startup-recovery",
      sessionRole: connectingSceneSession.role
    )
    recovery.delegateClass = StartupRecoverySceneDelegate.self
    recovery.storyboard = nil
    return recovery
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    guard !confirmedPreviousBuildFatal,
          !nativeActivationOnly,
          nativeActivationFailureCode.isEmpty
    else {
      assertionFailure("Flutter engine initialized behind native startup recovery gate")
      return
    }
    NSLog("QWQStartup ios_implicit_flutter_engine_initialized")
    window?.rootViewController?.view.backgroundColor = StartupTransitionBackground.color
    registerStartupTimingsChannel(
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    // 必须绑定 Flutter 创建的真实 implicit engine；在 didFinishLaunching 中访问
    // AppDelegate registrar 会提前运行 launch engine，随后 storyboard 再次启动同一 engine。
    configureIncomingCallInfrastructure(pluginRegistry: engineBridge.pluginRegistry)
    // Dart bootstrap 会在首帧前通过 cache manager 使用 sqflite。所有 generated plugins
    // 必须在 Dart entrypoint 启动前同步注册，不能延迟到首帧之后。
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    NSLog("QWQStartup ios_generated_plugins_registered_before_dart")
    registerMethodChannels(
      binaryMessenger: engineBridge.applicationRegistrar.messenger(),
      includeStartupTimings: false
    )
    observeNativeFlutterFirstFrame(
      window?.rootViewController as? FlutterViewController
    )
  }

  private func consumePendingActivationRequest()
    -> NativeRuntimeConfigActivationConsumeResult
  {
    NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
      arguments: ProcessInfo.processInfo.arguments,
      coldStartAllowed: true
    )
  }

  private func registerMethodChannels(
    binaryMessenger: FlutterBinaryMessenger,
    includeStartupTimings: Bool = true
  ) {
    if includeStartupTimings {
      registerStartupTimingsChannel(binaryMessenger: binaryMessenger)
    }

    let runtimeConfigChannel = FlutterMethodChannel(
      name: "quwoquan/runtime/config",
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
          NSLog("QWQStartup ios_runtime_config_internal_failure error=%@", "\(error)")
          DispatchQueue.main.async {
            result(FlutterError(
              code: NativeRuntimeConfigReadError.internalFailure.flutterCode,
              message: "Native runtime configuration operation failed.",
              details: nil
            ))
          }
        }
      }
    }

    let videoEditingChannel = FlutterMethodChannel(
      name: "quwoquan/video_editing",
      binaryMessenger: binaryMessenger
    )
    videoEditingChannel.setMethodCallHandler { [weak self] call, result in
      self?.videoEditingPlugin.handle(call: call, result: result)
    }

    let assistantChannel = FlutterMethodChannel(
      name: "personal_assistant/native_api",
      binaryMessenger: binaryMessenger
    )
    assistantChannel.setMethodCallHandler { [weak self] call, result in
      self?.personalAssistantNativeApiPlugin.handle(call: call, result: result)
    }

    let assistantDeviceActionChannel = FlutterMethodChannel(
      name: "quwoquan/assistant/device_action",
      binaryMessenger: binaryMessenger
    )
    assistantDeviceActionChannel.setMethodCallHandler { [weak self] call, result in
      self?.assistantDeviceActionPlugin.handle(call: call, result: result)
    }

    let nativeAuthChannel = FlutterMethodChannel(
      name: "quwoquan/auth/native_bridge",
      binaryMessenger: binaryMessenger
    )
    nativeAuthChannel.setMethodCallHandler { [weak self] call, result in
      self?.commercialAuthPlugin.handle(call: call, result: result)
    }

    let oneTapLoginChannel = FlutterMethodChannel(
      name: "quwoquan/auth/one_tap",
      binaryMessenger: binaryMessenger
    )
    oneTapLoginChannel.setMethodCallHandler { [weak self] call, result in
      self?.aliyunOneTapPlugin.handle(call: call, result: result)
    }

    let cellularGenerationChannel = FlutterMethodChannel(
      name: "quwoquan/network/cellular_generation",
      binaryMessenger: binaryMessenger
    )
    cellularGenerationChannel.setMethodCallHandler { [weak self] call, result in
      guard call.method == "readGeneration" else {
        result(FlutterMethodNotImplemented)
        return
      }
      result(self?.readCellularGeneration() ?? "unknown")
    }

    let nativeCrashMarkerChannel = FlutterMethodChannel(
      name: "quwoquan/runtime/native_crash_marker",
      binaryMessenger: binaryMessenger
    )
    nativeCrashMarkerChannel.setMethodCallHandler { call, result in
      if call.method == "consumePreviousCrash" {
        result(NativeCrashMarkerStore.consume())
        return
      }
      if call.method == "readPreviousAnr" {
        if #available(iOS 14.0, *) {
          result(NativeHangMetricStore.shared.read())
        } else {
          result(nil)
        }
        return
      }
      if call.method == "acknowledgePreviousAnr" {
        guard #available(iOS 14.0, *),
              let arguments = call.arguments as? [String: Any],
              let occurredAtEpochMs = arguments["occurredAtEpochMs"] as? NSNumber
        else {
          result(false)
          return
        }
        result(
          NativeHangMetricStore.shared.acknowledge(
            occurredAtEpochMs: occurredAtEpochMs.int64Value
          )
        )
        return
      }
      result(FlutterMethodNotImplemented)
    }

    let appRecoveryChannel = FlutterMethodChannel(
      name: "quwoquan/app_recovery",
      binaryMessenger: binaryMessenger
    )
    appRecoveryChannel.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        result(false)
        return
      }
      switch call.method {
      case "getRecoveryContext":
        let appVersion = Bundle.main.object(
          forInfoDictionaryKey: "CFBundleShortVersionString"
        ) as? String ?? ""
        let buildNumber = Bundle.main.object(
          forInfoDictionaryKey: "CFBundleVersion"
        ) as? String ?? ""
        result([
          "platform": "ios",
          "appVersion": appVersion,
          "buildNumber": buildNumber,
          "osVersion": UIDevice.current.systemVersion,
          "deviceModel": UIDevice.current.model,
          "environment": self.nativeRuntimeEnvironment,
          "recoveryBaseUrl": self.recoveryBaseURLString,
          "runtimeConfigDigest": self.nativeActiveRuntimePackageDigest,
          "effectiveLaunchManifestDigest": self.nativeEffectiveLaunchManifestDigest,
          "publicWebUrl": self.publicWebURLString,
          "appDownloadBaseUrl": self.appDownloadBaseURLString,
        ])
      case "openTrustedExternalUrl":
        guard let arguments = call.arguments as? [String: Any],
              let rawURL = arguments["url"] as? String,
              let url = URL(string: rawURL),
              self.isTrustedRecoveryURL(url)
        else {
          result(false)
          return
        }
        UIApplication.shared.open(url, options: [:]) { opened in
          result(opened)
        }
      case "recordFatalStartup":
        guard let arguments = call.arguments as? [String: Any] else {
          NSLog("QWQStartup startup_fatal_marker_ignored reason=attempt_mismatch")
          result(false)
          return
        }
        result(recordCurrentDartAttemptFatal(
          attemptId: arguments["attemptId"] as? String,
          failureCode: arguments["failureCode"] as? String
        ))
      case "readPendingNativeStartupFatal":
        result(NativeCrashMarkerStore.pendingFatal())
      case "ackPendingNativeStartupFatal":
        NativeCrashMarkerStore.acknowledgePendingFatal()
        result(nil)
      case "readRecoveryFailureQueue":
        DispatchQueue.global(qos: .utility).async {
          let value = self.recoveryFailureEncryptedStore.read()
          DispatchQueue.main.async { result(value) }
        }
      case "writeRecoveryFailureQueue":
        let value = (call.arguments as? [String: Any])?["value"] as? String ?? ""
        DispatchQueue.global(qos: .utility).async {
          let written = self.recoveryFailureEncryptedStore.write(value)
          DispatchQueue.main.async { result(written) }
        }
      case "clearRecoveryFailureQueue":
        DispatchQueue.global(qos: .utility).async {
          let cleared = self.recoveryFailureEncryptedStore.clear()
          DispatchQueue.main.async { result(cleared) }
        }
      default:
        result(FlutterMethodNotImplemented)
      }
    }

    let deferredPluginsChannel = FlutterMethodChannel(
      name: "quwoquan/startup/deferred_plugins",
      binaryMessenger: binaryMessenger
    )
    deferredPluginsChannel.setMethodCallHandler { [weak self] call, result in
      guard call.method == "ensureStartupPostFirstFrame" else {
        result(FlutterMethodNotImplemented)
        return
      }
      // 此调用只从 Dart 已完成 Shell 首帧的 scheduler 发起，统一同步首帧证据。
      self?.confirmFlutterFirstFrame(source: "safe_terminal")
      result(nil)
    }
  }

  private func readCellularGeneration() -> String {
    var technologies: [String] = []
    if #available(iOS 12.0, *) {
      if let technologiesByService = cellularNetworkInfo.serviceCurrentRadioAccessTechnology {
        technologies = Array(technologiesByService.values)
      }
    }
    if technologies.isEmpty, let current = cellularNetworkInfo.currentRadioAccessTechnology {
      technologies = [current]
    }
    if #available(iOS 14.1, *) {
      if technologies.contains(CTRadioAccessTechnologyNR)
        || technologies.contains(CTRadioAccessTechnologyNRNSA)
      {
        return "g5"
      }
    }
    return technologies.contains(CTRadioAccessTechnologyLTE) ? "g4" : "unknown"
  }

  private func isTrustedRecoveryURL(_ url: URL?) -> Bool {
    guard let url,
          url.scheme?.lowercased() == "https",
          url.user == nil,
          url.fragment == nil,
          let host = url.host?.lowercased()
    else {
      return false
    }
    return configuredTrustedRecoveryBases.contains { base in
      guard base.scheme?.lowercased() == "https",
            base.host?.lowercased() == host,
            (base.port ?? 443) == (url.port ?? 443)
      else {
        return false
      }
      let basePath = base.path.replacingOccurrences(
        of: "/+$",
        with: "",
        options: .regularExpression
      )
      return basePath.isEmpty
        || url.path == basePath
        || url.path.hasPrefix("\(basePath)/")
    }
  }

  private var configuredTrustedRecoveryBases: [URL] {
    let manifestValues = [
      nativeRuntimeManifest["recoveryBaseURL"] as? String,
      nativeRuntimeManifest["publicWebURL"] as? String,
      nativeRuntimeManifest["appDownloadBaseURL"] as? String,
    ]
    return manifestValues.compactMap { rawValue in
      guard let value = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines),
            !value.isEmpty
      else {
        return nil
      }
      return URL(string: value)
    }
  }
  private func registerStartupTimingsChannel(
    binaryMessenger: FlutterBinaryMessenger
  ) {
    let startupTimingsChannel = FlutterMethodChannel(
      name: "quwoquan/startup/timings",
      binaryMessenger: binaryMessenger
    )
    startupTimingsChannel.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        result(nil)
        return
      }
      if call.method == "recordStartupEvent" {
        let event = call.arguments as? String ?? "{}"
        self.logSafeStartupEvent(event)
        if event.contains("\"eventName\":\"flutter_first_frame\"") {
          self.confirmFlutterFirstFrame(source: "dart_channel")
        }
        if event.contains("\"eventName\":\"startup_safe_terminal\"") {
          self.confirmStartupSafeTerminal(reportedElapsedMs: self.startupEventElapsedMs(event))
        }
        result(nil)
        return
      }
      if call.method == "readStartupJournal" {
        result([
          "attemptId": self.startupTelemetryJournal.currentAttemptId,
          "events": self.startupTelemetryJournal.events(),
        ])
        return
      }
      if call.method == "clearStartupJournal" {
        self.startupTelemetryJournal.clearEvents()
        result(nil)
        return
      }
      guard call.method == "beginStartupAttempt" else {
        result(FlutterMethodNotImplemented)
        return
      }
      let arguments = call.arguments as? [String: Any]
      let attemptId = self.safeStartupIdentifier(arguments?["attemptId"] as? String)
      guard attemptId != "unknown" else {
        result(
          FlutterError(
            code: "invalid_startup_attempt",
            message: "attemptId is required",
            details: nil
          )
        )
        return
      }
      let now = ProcessInfo.processInfo.systemUptime
      let hotRestart = self.dartStartupAttemptStarted
      self.dartStartupAttemptStarted = true
      self.currentDartAttemptId = attemptId
      self.currentDartAttemptIsHotRestart = hotRestart
      self.currentDartAttemptStartedUptime = hotRestart ? now : self.processStartUptime
      let processElapsedMs = Int((now - self.processStartUptime) * 1000)
      let attemptElapsedMs = Int((now - self.currentDartAttemptStartedUptime) * 1000)
      result([
        "elapsedSinceProcessStartMs": processElapsedMs,
        "elapsedSinceAttemptStartMs": attemptElapsedMs,
        "attemptKind": hotRestart ? "hotRestart" : "cold",
        "deadlineOrigin": hotRestart ? "dartHotRestart" : "nativeProcess",
        "startupAttemptId": attemptId,
      ])
    }
  }

  private func logSafeStartupEvent(_ rawEvent: String) {
    guard let data = rawEvent.data(using: .utf8),
          let object = try? JSONSerialization.jsonObject(with: data),
          let event = object as? [String: Any],
          let eventName = event["eventName"] as? String
    else {
      return
    }
    if eventName == "startup_attempt_started" {
      let reportedAttemptId = safeStartupIdentifier(event["attemptId"] as? String)
      guard reportedAttemptId == currentDartAttemptId else {
        NSLog("QWQStartup ios_dart_startup_attempt_invalid reason=attempt_mismatch")
        return
      }
      currentLaunchMode = safeStartupEnum(event["launchMode"] as? String)
      let configurationState = safeStartupEnum(
        event["configurationState"] as? String
      )
      let missingDefineKeys = safeDefineKeyList(event["missingDefineKeys"] as? String)
      NSLog(
        "QWQStartup ios_dart_startup_attempt attemptId=%@ launchMode=%@ hotRestart=%@ configurationState=%@ effectiveLaunchManifestDigest=%@%@",
        currentDartAttemptId,
        currentLaunchMode,
        currentDartAttemptIsHotRestart ? "true" : "false",
        configurationState,
        NativeCrashMarkerStore.effectiveLaunchManifestDigest,
        missingDefineKeys.isEmpty ? "" : " missingDefineKeys=\(missingDefineKeys)"
      )
      return
    }
    if eventName == "startup_bootstrap_failure" {
      // bootstrap 根已经显示 Flutter recovery；只输出固定 terminal 标识，
      // 不转写失败详情、异常内容或用户态上下文。
      let failureCode = safeStartupFailureCode(event["failureCode"] as? String)
      let missingDefineKeys = safeDefineKeyList(event["missingDefineKeys"] as? String)
      NSLog(
        "QWQStartup ios_startup_bootstrap_failure attemptId=%@ launchMode=%@%@%@",
        currentDartAttemptId,
        currentLaunchMode,
        failureCode.isEmpty ? "" : " failureCode=\(failureCode)",
        missingDefineKeys.isEmpty ? "" : " missingDefineKeys=\(missingDefineKeys)"
      )
      NSLog("QWQStartup startup_probe phase=safe_recovery_shown")
      return
    }
    guard eventName == "startup_welcome_sequence" else {
      NSLog("QWQStartup startup_event_received eventName=%@", eventName)
      return
    }
    logSafeStartupProbeTerminal(event)
    // 原生层只确认 Flutter 启动事件到达；probe 仅可见终态，不镜像动效 phase/replay。
    NSLog("QWQStartup startup_event_received eventName=startup_welcome_sequence")
  }

  private func recordCurrentDartAttemptFatal(
    attemptId rawAttemptId: String?,
    failureCode rawFailureCode: String?
  ) -> Bool {
    let attemptId = safeStartupIdentifier(rawAttemptId)
    let failureCode = safeStartupFailureCode(rawFailureCode)
    guard attemptId != "unknown",
          !failureCode.isEmpty,
          attemptId == currentDartAttemptId
    else {
      NSLog("QWQStartup startup_fatal_marker_ignored reason=attempt_mismatch")
      return false
    }
    guard !currentDartAttemptIsHotRestart else {
      NSLog("QWQStartup startup_fatal_marker_ignored reason=hot_restart")
      return false
    }
    guard !startupSafeTerminalConfirmed else {
      NSLog("QWQStartup startup_fatal_marker_ignored reason=safe_shell_reached")
      return false
    }
    guard NativeCrashMarkerStore.markFatalStartup() else {
      NSLog("QWQStartup startup_fatal_marker_ignored reason=artifact_mismatch")
      return false
    }
    NSLog("QWQStartup startup_fatal_marker_recorded")
    return true
  }

  private func logSafeStartupProbeTerminal(_ event: [String: Any]) {
    guard let phase = event["phase"] as? String else { return }
    switch phase {
    case "finished":
      guard let welcomeExitMs = safeStartupProbeDuration(
        event,
        preferredField: "welcomeExitMs"
      ) else {
        return
      }
      let exitReason = safeStartupProbeExitReason(event["exitReason"] as? String)
      NSLog(
        "QWQStartup startup_probe phase=finished welcomeExitMs=%d%@",
        welcomeExitMs,
        exitReason.isEmpty ? "" : " exitReason=\(exitReason)"
      )
    case "main_shell_first_paint":
      guard let shellFirstPaintMs = safeStartupProbeDuration(
        event,
        preferredField: "shellFirstPaintMs"
      ) else {
        return
      }
      NSLog(
        "QWQStartup startup_probe phase=main_shell_first_paint shellFirstPaintMs=%d",
        shellFirstPaintMs
      )
    case "welcome_overlay_removed":
      guard let overlayRemovedMs = safeStartupProbeDuration(
        event,
        preferredField: "overlayRemovedMs"
      ) else {
        return
      }
      NSLog(
        "QWQStartup startup_probe phase=welcome_overlay_removed overlayRemovedMs=%d",
        overlayRemovedMs
      )
    case "safe_recovery_shown":
      let failureCode = safeStartupFailureCode(event["failureCode"] as? String)
      NSLog(
        "QWQStartup startup_probe phase=safe_recovery_shown%@",
        failureCode.isEmpty ? "" : " failureCode=\(failureCode)"
      )
    default:
      return
    }
  }

  private func safeStartupProbeDuration(
    _ event: [String: Any],
    preferredField: String
  ) -> Int? {
    for field in [preferredField, "elapsedSinceProcessStartMs"] {
      guard let value = event[field] as? NSNumber else { continue }
      let duration = value.intValue
      if duration >= 0 && duration <= 300_000 {
        return duration
      }
    }
    return nil
  }

  private func safeStartupProbeExitReason(_ value: String?) -> String {
    guard let value else { return "" }
    switch value {
    case "ready_primary", "ready_replay", "deadline", "deadline_fallback":
      return value
    default:
      return ""
    }
  }

  private func safeStartupIdentifier(_ value: String?) -> String {
    guard let value, !value.isEmpty, value.count <= 128 else { return "unknown" }
    let allowed = CharacterSet.alphanumerics.union(
      CharacterSet(charactersIn: "_-")
    )
    guard value.rangeOfCharacter(from: allowed.inverted) == nil else {
      return "unknown"
    }
    return value
  }

  private func safeStartupEnum(_ value: String?) -> String {
    guard let value, !value.isEmpty, value.count <= 64 else { return "unknown" }
    let allowed = CharacterSet.alphanumerics.union(
      CharacterSet(charactersIn: "_-")
    )
    guard value.rangeOfCharacter(from: allowed.inverted) == nil else {
      return "unknown"
    }
    return value
  }

  private func safeDefineKeyList(_ value: String?) -> String {
    guard let value, !value.isEmpty, value.count <= 512 else { return "" }
    let allowed = CharacterSet.alphanumerics.union(
      CharacterSet(charactersIn: "_,")
    )
    guard value.rangeOfCharacter(from: allowed.inverted) == nil else {
      return ""
    }
    return value
  }

  private func safeStartupFailureCode(_ value: String?) -> String {
    guard let value, !value.isEmpty, value.count <= 128 else { return "" }
    let allowed = CharacterSet.alphanumerics.union(
      CharacterSet(charactersIn: "._-")
    )
    guard value.rangeOfCharacter(from: allowed.inverted) == nil else {
      return ""
    }
    return value
  }

  override func applicationDidBecomeActive(_ application: UIApplication) {
    if nativeActivationOnly {
      return
    }
    if !confirmedPreviousBuildFatal && nativeActivationFailureCode.isEmpty {
      super.applicationDidBecomeActive(application)
    }
    if !appInForeground {
      appInForeground = true
      foregroundStartedUptime = ProcessInfo.processInfo.systemUptime
    }
    if recoveryExternalReturnPending && confirmedPreviousBuildFatal {
      recoveryExternalReturnPending = false
      NSLog(
        "QWQStartup ios_native_recovery_external_returned processId=%d",
        ProcessInfo.processInfo.processIdentifier
      )
    }
    if recoveryVersionRefreshPending,
       nativeRecoveryShown,
       let title = startupRecoveryTitle,
       let message = startupRecoveryMessage,
       let primary = startupRecoveryPrimary,
       let web = startupRecoveryWeb
    {
      recoveryVersionRefreshPending = false
      checkNativeRecoveryVersion(
        titleLabel: title,
        messageLabel: message,
        primaryButton: primary,
        webButton: web
      )
    }
    if !confirmedPreviousBuildFatal && nativeActivationFailureCode.isEmpty {
      armFlutterFirstFrameWatchdog()
    }
  }

  override func applicationWillResignActive(_ application: UIApplication) {
    if appInForeground && !startupSafeTerminalConfirmed {
      _ = consumeForegroundFirstFrameBudget(
        now: ProcessInfo.processInfo.systemUptime
      )
    }
    appInForeground = false
    foregroundStartedUptime = 0
    cancelFlutterFirstFrameWatchdog()
    if !confirmedPreviousBuildFatal,
       !nativeActivationOnly,
       nativeActivationFailureCode.isEmpty
    {
      super.applicationWillResignActive(application)
    }
  }

  override func applicationWillTerminate(_ application: UIApplication) {
    cancelFlutterFirstFrameWatchdog()
    cancelNativeRecoveryTerminalReconciliation()
    if !confirmedPreviousBuildFatal,
       !nativeActivationOnly,
       nativeActivationFailureCode.isEmpty
    {
      super.applicationWillTerminate(application)
    }
  }

  private func observeNativeFlutterFirstFrame(
    _ controller: FlutterViewController?
  ) {
    controller?.setFlutterViewDidRenderCallback { [weak self] in
      self?.confirmFlutterFirstFrame(source: "renderer")
    }
  }

  private func confirmFlutterFirstFrame(source: String) {
    // renderer 首帧是 native watchdog 的物理事实；Dart channel 仅作幂等补充。
    // 迟到首帧仍须记账；recovery 撤销由 safe_terminal 负责。
    if !flutterFirstFrameConfirmed {
      flutterFirstFrameConfirmed = true
    }
    let elapsedMs = Int(
      (ProcessInfo.processInfo.systemUptime - currentDartAttemptStartedUptime) * 1000
    )
    NSLog(
      "QWQStartup ios_flutter_first_frame elapsedMs=%d source=%@ attemptId=%@ nativeAttemptId=%@ launchMode=%@",
      elapsedMs,
      source,
      currentDartAttemptId.isEmpty
        ? startupTelemetryJournal.currentAttemptId
        : currentDartAttemptId,
      startupTelemetryJournal.currentAttemptId,
      currentLaunchMode
    )
  }

  private func startupEventElapsedMs(_ event: String) -> Int? {
    guard let data = event.data(using: .utf8),
          let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let elapsedMs = object["elapsedMs"] as? NSNumber
    else {
      return nil
    }
    return elapsedMs.intValue
  }

  private func confirmStartupSafeTerminal(reportedElapsedMs: Int?) {
    // MethodChannel 可能比 watchdog 主线程任务晚几毫秒。只要 Flutter 已到
    // routerShell / recovery 安全面，就必须取消看门狗并撤销竞态恢复层。
    let firstNativeSafeTerminal = !startupSafeTerminalConfirmed
    if firstNativeSafeTerminal {
      startupSafeTerminalConfirmed = true
      if !confirmedPreviousBuildFatal {
        NativeCrashMarkerStore.markSafeShell()
      }
      cancelFlutterFirstFrameWatchdog()
      cancelNativeRecoveryTerminalReconciliation()
      dismissNativeStartupRecoveryForSafeTerminalRace()
    }
    let receivedElapsedMs = Int(
      (ProcessInfo.processInfo.systemUptime - currentDartAttemptStartedUptime) * 1000
    )
    let reportedMs = max(0, reportedElapsedMs ?? receivedElapsedMs)
    let exceedsDeadline =
      reportedMs > Int(Self.flutterFirstFrameDeadline * 1000)
      || receivedElapsedMs > Int(Self.flutterFirstFrameDeadline * 1000)
    NSLog(
      "QWQStartup ios_startup_safe_terminal reportedElapsedMs=%d receivedMs=%d attemptId=%@ nativeAttemptId=%@ launchMode=%@",
      reportedMs,
      receivedElapsedMs,
      currentDartAttemptId.isEmpty
        ? startupTelemetryJournal.currentAttemptId
        : currentDartAttemptId,
      startupTelemetryJournal.currentAttemptId,
      currentLaunchMode
    )
    if exceedsDeadline {
      NSLog(
        "QWQStartup ios_startup_safe_terminal_slow reportedElapsedMs=%d receivedMs=%d attemptId=%@",
        reportedMs,
        receivedElapsedMs,
        currentDartAttemptId
      )
    }
  }

  private func dismissNativeStartupRecoveryForSafeTerminalRace() {
    guard nativeRecoveryShown else {
      nativeRecoveryDeadlineReached = false
      return
    }
    startupRecoveryView?.removeFromSuperview()
    startupRecoveryView = nil
    nativeRecoveryShown = false
    nativeRecoveryDeadlineReached = false
    NSLog("QWQStartup ios_startup_safe_terminal_race_dismissed")
  }

  private func armFlutterFirstFrameWatchdog() {
    guard !startupSafeTerminalConfirmed,
          !nativeRecoveryShown,
          !nativeRecoveryDeadlineReached,
          appInForeground
    else {
      return
    }
    cancelFlutterFirstFrameWatchdog()
    let remaining = consumeForegroundFirstFrameBudget(
      now: ProcessInfo.processInfo.systemUptime
    )
    guard remaining > 0 else {
      triggerNativeFirstFrameDeadline()
      return
    }
    let watchdog = DispatchWorkItem { [weak self] in
      self?.triggerNativeFirstFrameDeadline()
    }
    flutterFirstFrameWatchdog = watchdog
    DispatchQueue.main.asyncAfter(deadline: .now() + remaining, execute: watchdog)
  }

  private func cancelFlutterFirstFrameWatchdog() {
    flutterFirstFrameWatchdog?.cancel()
    flutterFirstFrameWatchdog = nil
  }

  private func scheduleNativeRecoveryTerminal(
    elapsedMs: Int,
    firstFrameMissing: Bool
  ) {
    cancelNativeRecoveryTerminalReconciliation()
    let reconciliation = DispatchWorkItem { [weak self] in
      guard let self,
            !self.startupSafeTerminalConfirmed,
            self.nativeRecoveryShown,
            self.nativeRecoveryDeadlineReached
      else {
        return
      }
      self.recordNativeStartupTerminal(
        elapsedMs: elapsedMs,
        firstFrameMissing: firstFrameMissing
      )
    }
    nativeRecoveryTerminalReconciliation = reconciliation
    DispatchQueue.main.asyncAfter(
      deadline: .now() + .milliseconds(120),
      execute: reconciliation
    )
  }

  private func cancelNativeRecoveryTerminalReconciliation() {
    nativeRecoveryTerminalReconciliation?.cancel()
    nativeRecoveryTerminalReconciliation = nil
  }

  private func consumeForegroundFirstFrameBudget(now: TimeInterval) -> TimeInterval {
    guard appInForeground, !startupSafeTerminalConfirmed else {
      return firstFrameForegroundRemaining
    }
    if foregroundStartedUptime > 0 {
      let elapsed = max(0, now - foregroundStartedUptime)
      firstFrameForegroundRemaining = max(0, firstFrameForegroundRemaining - elapsed)
      foregroundStartedUptime = now
    }
    return firstFrameForegroundRemaining
  }

  private func triggerNativeFirstFrameDeadline() {
    guard !startupSafeTerminalConfirmed,
          !nativeRecoveryShown,
          !nativeRecoveryDeadlineReached,
          appInForeground
    else {
      return
    }
    let elapsedMs = Int((ProcessInfo.processInfo.systemUptime - processStartUptime) * 1000)
    // 主线程再次核对，避免 MethodChannel 晚几毫秒导致假阳性 nativeRecovery。
    DispatchQueue.main.async { [weak self] in
      guard let self else { return }
      guard !self.startupSafeTerminalConfirmed,
            !self.nativeRecoveryShown,
            !self.nativeRecoveryDeadlineReached,
            self.appInForeground
      else {
        return
      }
      self.nativeRecoveryDeadlineReached = true
      self.recordNativeStartupDeadline(
        elapsedMs: elapsedMs,
        firstFrameMissing: !self.flutterFirstFrameConfirmed
      )
    }
  }

  private func recordNativeStartupDeadline(
    elapsedMs: Int,
    firstFrameMissing: Bool
  ) {
    let outcome = firstFrameMissing ? "native_first_frame_timeout" : "startup_deadline"
    let timeoutLog = firstFrameMissing
      ? "ios_native_first_frame_timeout"
      : "ios_startup_safe_terminal_timeout"
    NSLog(
      "QWQStartup %@ elapsedMs=%d attemptId=%@",
      timeoutLog,
      elapsedMs,
      startupTelemetryJournal.currentAttemptId
    )
    startupTelemetryJournal.record(
      phase: "performance",
      elapsedMs: elapsedMs,
      outcome: outcome,
      failureSource: "native_watchdog"
    )
  }

  private func recordNativeStartupTerminal(
    elapsedMs: Int,
    firstFrameMissing: Bool
  ) {
    guard !startupSafeTerminalConfirmed else { return }
    let failureCode = firstFrameMissing
      ? "OPS.SYSTEM.startup_native_first_frame_timeout"
      : "OPS.SYSTEM.startup_initialization_failed"
    startupTelemetryJournal.record(
      phase: "terminal",
      elapsedMs: elapsedMs,
      outcome: "recovery",
      failureCode: failureCode,
      failureSource: "native_watchdog"
    )
  }

  private func enqueueConfirmedStartupFatal() -> Bool {
    guard NativeCrashMarkerStore.fatalNeedsQueueing(),
          let pending = NativeCrashMarkerStore.pendingFatal(),
          let occurredAt = pending["occurredAt"],
          let errorType = pending["errorType"]
    else {
      return !NativeCrashMarkerStore.fatalNeedsQueueing()
    }

    let formatter = ISO8601DateFormatter()
    let now = Date()
    var retained: [[String: Any]] = []
    if let raw = recoveryFailureEncryptedStore.read(),
       let data = raw.data(using: .utf8),
       let decoded = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    {
      retained = decoded.filter { entry in
        guard let savedAt = entry["savedAt"] as? String,
              let savedDate = formatter.date(from: savedAt)
        else {
          return false
        }
        return now.timeIntervalSince(savedDate) <= Self.recoveryRetention
      }
    }

    let failure: [String: Any] = [
      "occurredAt": occurredAt,
      "appVersion": Bundle.main.object(
        forInfoDictionaryKey: "CFBundleShortVersionString"
      ) as? String ?? "",
      "buildNumber": NativeCrashMarkerStore.currentBuild,
      "platform": "ios",
      "osVersion": UIDevice.current.systemVersion,
      "deviceModel": UIDevice.current.model,
      "errorSource": "native",
      "errorType": errorType,
      "errorMessage": "Native startup terminated before safe shell",
      "stackTrace": "Native stack unavailable after process termination",
    ]
    guard let failureData = try? JSONSerialization.data(withJSONObject: failure),
          failureData.count <= Self.maximumRecoveryRecordBytes
    else {
      return false
    }
    retained.append([
      "failure": failure,
      "savedAt": occurredAt,
      "attempts": 0,
    ])
    if retained.count > Self.maximumRecoveryRecords {
      retained.removeFirst(retained.count - Self.maximumRecoveryRecords)
    }
    guard let output = try? JSONSerialization.data(withJSONObject: retained),
          let value = String(data: output, encoding: .utf8),
          recoveryFailureEncryptedStore.write(value)
    else {
      return false
    }
    NativeCrashMarkerStore.markFatalQueued()
    return true
  }

  func installNativeStartupRecoveryRoot(in sceneWindow: UIWindow? = nil) {
    let recoveryWindow = sceneWindow ?? window ?? UIWindow(frame: UIScreen.main.bounds)
    let root = UIViewController()
    root.view.backgroundColor = StartupTransitionBackground.color
    recoveryWindow.rootViewController = root
    recoveryWindow.backgroundColor = StartupTransitionBackground.color
    window = recoveryWindow
    recoveryWindow.makeKeyAndVisible()
  }

  func showNativeStartupRecovery() {
    guard (!startupSafeTerminalConfirmed
             || confirmedPreviousBuildFatal
             || !nativeActivationFailureCode.isEmpty),
          !nativeRecoveryShown,
          let window
    else { return }
    nativeRecoveryShown = true

    let recovery = UIView(frame: window.bounds)
    recovery.accessibilityIdentifier = "qwq.native.startup.recovery"
    let backgroundColor = UIColor(
      red: 247 / 255,
      green: 247 / 255,
      blue: 252 / 255,
      alpha: 1
    )
    recovery.backgroundColor = backgroundColor
    recovery.autoresizingMask = [.flexibleWidth, .flexibleHeight]
    window.backgroundColor = backgroundColor

    let title = UILabel()
    title.text = "应用暂时无法启动"
    title.textColor = UIColor(
      red: 17 / 255,
      green: 19 / 255,
      blue: 24 / 255,
      alpha: 1
    )
    title.font = .systemFont(ofSize: 28, weight: .semibold)
    title.textAlignment = .center
    title.translatesAutoresizingMaskIntoConstraints = false

    let message = UILabel()
    message.text = "正在检查可用版本"
    message.textColor = UIColor(
      red: 107 / 255,
      green: 112 / 255,
      blue: 124 / 255,
      alpha: 1
    )
    message.font = .systemFont(ofSize: 17, weight: .regular)
    message.numberOfLines = 0
    message.textAlignment = .center
    message.translatesAutoresizingMaskIntoConstraints = false

    let primary = RecoveryActionButton(type: .system)
    primary.accessibilityIdentifier = "qwq.native.startup.recovery.primary"
    configureRecoveryButton(primary, title: "正在检查…", filled: true, enabled: false)

    let web = RecoveryActionButton(type: .system)
    web.accessibilityIdentifier = "qwq.native.startup.recovery.web"
    configureRecoveryButton(web, title: "使用网页版", filled: false, enabled: true)
    web.recoveryAction = { [weak self] in
      self?.openRecoveryTarget(
        self?.publicWebURLString ?? "",
        fallback: "",
        failureMessage: "网页暂时无法打开，请稍后再试"
      )
    }

    let stack = UIStackView(arrangedSubviews: [title, message, primary, web])
    stack.axis = .vertical
    stack.alignment = .fill
    stack.distribution = .fill
    stack.setCustomSpacing(16, after: title)
    stack.setCustomSpacing(28, after: message)
    stack.setCustomSpacing(12, after: primary)
    stack.translatesAutoresizingMaskIntoConstraints = false
    recovery.addSubview(stack)
    NSLayoutConstraint.activate([
      stack.centerXAnchor.constraint(equalTo: recovery.centerXAnchor),
      NSLayoutConstraint(
        item: stack,
        attribute: .centerY,
        relatedBy: .equal,
        toItem: recovery,
        attribute: .bottom,
        multiplier: 0.55,
        constant: 0
      ),
      stack.widthAnchor.constraint(lessThanOrEqualToConstant: 280),
      stack.leadingAnchor.constraint(greaterThanOrEqualTo: recovery.leadingAnchor, constant: 24),
      stack.trailingAnchor.constraint(lessThanOrEqualTo: recovery.trailingAnchor, constant: -24),
      title.heightAnchor.constraint(equalToConstant: 44),
      message.heightAnchor.constraint(equalToConstant: 52),
      primary.heightAnchor.constraint(equalToConstant: 48),
      web.heightAnchor.constraint(equalToConstant: 48),
    ])
    window.addSubview(recovery)
    startupRecoveryView = recovery
    startupRecoveryTitle = title
    startupRecoveryMessage = message
    startupRecoveryPrimary = primary
    startupRecoveryWeb = web
    checkNativeRecoveryVersion(
      titleLabel: title,
      messageLabel: message,
      primaryButton: primary,
      webButton: web
    )
  }

  private func configureRecoveryButton(
    _ button: RecoveryActionButton,
    title: String,
    filled: Bool,
    enabled: Bool
  ) {
    button.setTitle(title, for: .normal)
    button.titleLabel?.font = .systemFont(ofSize: 17, weight: .medium)
    button.isEnabled = enabled
    button.layer.cornerRadius = 24
    button.layer.borderWidth = filled ? 0 : 1
    button.layer.borderColor = UIColor(
      red: 8 / 255,
      green: 123 / 255,
      blue: 1,
      alpha: 1
    ).cgColor
    if filled {
      button.backgroundColor = enabled
        ? UIColor(red: 8 / 255, green: 123 / 255, blue: 1, alpha: 1)
        : UIColor(red: 233 / 255, green: 237 / 255, blue: 245 / 255, alpha: 1)
      button.setTitleColor(
        enabled ? .white : UIColor(red: 107 / 255, green: 112 / 255, blue: 124 / 255, alpha: 1),
        for: .normal
      )
    } else {
      button.backgroundColor = .clear
      button.setTitleColor(UIColor(red: 8 / 255, green: 123 / 255, blue: 1, alpha: 1), for: .normal)
    }
  }

  private var recoveryBaseURLString: String {
    guard let value = nativeRuntimeManifest["recoveryBaseURL"] as? String,
          isTrustedRecoveryURL(URL(string: value))
    else {
      return ""
    }
    return value
  }

  private var publicWebURLString: String {
    guard let value = nativeRuntimeManifest["publicWebURL"] as? String,
          isTrustedRecoveryURL(URL(string: value))
    else {
      return ""
    }
    return value
  }

  private var appDownloadBaseURLString: String {
    guard let value = nativeRuntimeManifest["appDownloadBaseURL"] as? String,
          isTrustedRecoveryURL(URL(string: value))
    else {
      return ""
    }
    return value
  }

  private var nativeRuntimeEnvironment: String {
    guard let value = nativeRuntimeManifest["runtimeEnvironment"] as? String,
          ["alpha", "beta", "gamma", "prod"].contains(value)
    else {
      return ""
    }
    return value
  }

  private var nativeActiveRuntimePackageDigest: String {
    (nativeRuntimeManifest["runtimeConfigDigest"] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
  }

  private var nativeEffectiveLaunchManifestDigest: String {
    (nativeRuntimeManifest["effectiveLaunchManifestDigest"] as? String)?
      .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
  }

  private var nativeRuntimeManifest: [String: Any] {
    switch NativeRuntimeConfigActivationCoordinator.readRecoveryRuntimeContext() {
    case .present(let manifest):
      return manifest
    case .absent:
      return [:]
    case .failure(let code):
      NSLog("QWQStartup ios_runtime_config_recovery_context_failed code=%@", code)
      return ["runtimeConfigErrorCode": code]
    }
  }

  private func checkNativeRecoveryVersion(
    titleLabel: UILabel,
    messageLabel: UILabel,
    primaryButton: RecoveryActionButton,
    webButton: RecoveryActionButton
  ) {
    guard !recoveryVersionCheckInFlight else { return }
    recoveryVersionCheckInFlight = true
    guard var components = URLComponents(string: recoveryBaseURLString) else {
      recoveryVersionCheckInFlight = false
      applyNativeVersionUnavailable(
        titleLabel: titleLabel,
        messageLabel: messageLabel,
        primaryButton: primaryButton,
        webButton: webButton
      )
      return
    }
    components.path = "/ops/app-recovery/version"
    let appVersion = Bundle.main.object(
      forInfoDictionaryKey: "CFBundleShortVersionString"
    ) as? String ?? ""
    let buildNumber = NativeCrashMarkerStore.currentBuild
    components.queryItems = [
      URLQueryItem(name: "platform", value: "ios"),
      URLQueryItem(name: "appVersion", value: appVersion),
      URLQueryItem(name: "buildNumber", value: buildNumber),
    ]
    guard let url = components.url else {
      recoveryVersionCheckInFlight = false
      return
    }
    var request = URLRequest(url: url)
    request.cachePolicy = .reloadIgnoringLocalCacheData
    request.timeoutInterval = 1.5
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    let configuration = URLSessionConfiguration.ephemeral
    configuration.timeoutIntervalForRequest = 1.5
    URLSession(configuration: configuration).dataTask(with: request) { [weak self] data, response, _ in
      defer {
        DispatchQueue.main.async { [weak self] in
          self?.recoveryVersionCheckInFlight = false
        }
      }
      guard let self,
            let http = response as? HTTPURLResponse,
            (200..<300).contains(http.statusCode),
            let data,
            data.count <= 65_536,
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            payload.count == 4,
            let latestBuildRaw = payload["latestBuild"] as? String,
            let latestBuild = Int(latestBuildRaw),
            let updateRaw = payload["updateUrl"] as? String,
            let recoveryRaw = payload["recoveryUrl"] as? String,
            self.isTrustedRecoveryURL(URL(string: recoveryRaw)),
            latestBuild <= (Int(buildNumber) ?? 0)
              || self.isTrustedRecoveryURL(URL(string: updateRaw))
      else {
        DispatchQueue.main.async { [weak self] in
          self?.applyNativeVersionUnavailable(
            titleLabel: titleLabel,
            messageLabel: messageLabel,
            primaryButton: primaryButton,
            webButton: webButton
          )
        }
        return
      }
      DispatchQueue.main.async { [weak self] in
        guard let self else { return }
        if latestBuild > (Int(buildNumber) ?? 0) {
          titleLabel.text = "当前版本需要更新"
          messageLabel.text = "更新后即可正常启动"
          self.configureRecoveryButton(primaryButton, title: "前往更新", filled: true, enabled: true)
          primaryButton.recoveryAction = { [weak self] in
            self?.openRecoveryTarget(
              updateRaw,
              fallback: recoveryRaw,
              failureMessage: "暂时无法打开更新页面，请稍后再试",
              recheckVersionOnReturn: true
            )
          }
          webButton.isHidden = false
        } else {
          titleLabel.text = "当前已是最新版本"
          messageLabel.text = "请使用网页版继续"
          self.configureRecoveryButton(primaryButton, title: "使用网页版", filled: true, enabled: true)
          primaryButton.recoveryAction = { [weak self] in
            self?.openRecoveryTarget(
              self?.publicWebURLString ?? "",
              fallback: recoveryRaw,
              failureMessage: "网页暂时无法打开，请稍后再试"
            )
          }
          webButton.isHidden = true
        }
      }
    }.resume()
  }

  private func applyNativeVersionUnavailable(
    titleLabel: UILabel,
    messageLabel: UILabel,
    primaryButton: RecoveryActionButton,
    webButton: RecoveryActionButton
  ) {
    titleLabel.text = "应用暂时无法启动"
    messageLabel.text = "请使用网页版继续"
    configureRecoveryButton(primaryButton, title: "使用网页版", filled: true, enabled: true)
    primaryButton.recoveryAction = { [weak self] in
      self?.openRecoveryTarget(
        self?.publicWebURLString ?? "",
        fallback: "",
        failureMessage: "网页暂时无法打开，请稍后再试"
      )
    }
    webButton.isHidden = true
  }

  private func openRecoveryTarget(
    _ target: String,
    fallback: String,
    failureMessage: String,
    recheckVersionOnReturn: Bool = false
  ) {
    guard !recoveryExternalOpenInFlight else { return }
    recoveryExternalOpenInFlight = true
    openTrustedRecoveryURL(target) { [weak self] opened in
      guard let self else { return }
      if opened {
        self.recoveryVersionRefreshPending = recheckVersionOnReturn
        self.recoveryExternalOpenInFlight = false
        return
      }
      self.openTrustedRecoveryURL(fallback) { [weak self] fallbackOpened in
        guard let self else { return }
        self.recoveryExternalOpenInFlight = false
        if fallbackOpened {
          self.recoveryVersionRefreshPending = recheckVersionOnReturn
        } else {
          self.showRecoveryToast(failureMessage)
        }
      }
    }
  }

  private func openTrustedRecoveryURL(
    _ rawURL: String,
    completion: @escaping (Bool) -> Void
  ) {
    guard let url = URL(string: rawURL), isTrustedRecoveryURL(url) else {
      completion(false)
      return
    }
    let urlDigest = recoveryURLDigest(rawURL)
    NSLog(
      "QWQStartup ios_native_recovery_external_open_requested urlDigest=%@ processId=%d",
      urlDigest,
      ProcessInfo.processInfo.processIdentifier
    )
    UIApplication.shared.open(url, options: [:]) { opened in
      NSLog(
        "QWQStartup ios_native_recovery_external_open_completed urlDigest=%@ opened=%@",
        urlDigest,
        opened ? "true" : "false"
      )
      if opened {
        self.recoveryExternalReturnPending = true
      }
      completion(opened)
    }
  }

  private func recoveryURLDigest(_ rawURL: String) -> String {
    let digest = SHA256.hash(data: Data(rawURL.utf8))
    return "sha256:" + digest.map { String(format: "%02x", $0) }.joined()
  }

  private func showRecoveryToast(_ message: String) {
    guard let recovery = startupRecoveryView else { return }
    let toast = UILabel()
    toast.text = message
    toast.textAlignment = .center
    toast.numberOfLines = 0
    toast.textColor = .white
    toast.backgroundColor = UIColor.black.withAlphaComponent(0.78)
    toast.font = .systemFont(ofSize: 14)
    toast.layer.cornerRadius = 8
    toast.clipsToBounds = true
    toast.translatesAutoresizingMaskIntoConstraints = false
    recovery.addSubview(toast)
    NSLayoutConstraint.activate([
      toast.centerXAnchor.constraint(equalTo: recovery.centerXAnchor),
      toast.bottomAnchor.constraint(equalTo: recovery.safeAreaLayoutGuide.bottomAnchor, constant: -24),
      toast.widthAnchor.constraint(lessThanOrEqualToConstant: 300),
      toast.heightAnchor.constraint(greaterThanOrEqualToConstant: 44),
    ])
    UIView.animate(withDuration: 0.2, delay: 2, options: []) {
      toast.alpha = 0
    } completion: { _ in
      toast.removeFromSuperview()
    }
  }

  override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    if confirmedPreviousBuildFatal {
      return false
    }
    if commercialAuthPlugin.handle(url: url) {
      return true
    }
    return super.application(app, open: url, options: options)
  }

  override func application(
    _ application: UIApplication,
    continue userActivity: NSUserActivity,
    restorationHandler: @escaping ([UIUserActivityRestoring]?) -> Void
  ) -> Bool {
    if confirmedPreviousBuildFatal {
      return false
    }
    if commercialAuthPlugin.handle(userActivity: userActivity) {
      return true
    }
    return super.application(
      application,
      continue: userActivity,
      restorationHandler: restorationHandler
    )
  }
}

private enum StartupTransitionBackground {
  static let color = UIColor(
    red: 0.0392156863,
    green: 0.5176470588,
    blue: 1.0,
    alpha: 1
  )
}

final class AssistantDeviceActionPlugin {
  private static let recordPrefix = "qwq.device.calendar."
  let eventStore: EKEventStore
  private let defaults: UserDefaults

  init(
    eventStore: EKEventStore = EKEventStore(),
    defaults: UserDefaults = .standard
  ) {
    self.eventStore = eventStore
    self.defaults = defaults
  }

  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "probe":
      handleProbe(result: result)
    case "createEvent":
      handleMutation(operation: .create, arguments: call.arguments, result: result)
    case "updateEvent":
      handleMutation(operation: .update, arguments: call.arguments, result: result)
    case "deleteEvent":
      handleMutation(operation: .delete, arguments: call.arguments, result: result)
    case "createCalendarReminder":
      // The pre-M3 request has no opaque permit binding and must fail closed.
      result(failure(status: "unavailable"))
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func handleProbe(result: @escaping FlutterResult) {
    let permission = permissionStatus()
    guard permission == "granted" else {
      result(probe(permission: permission, hasWritableCalendar: false))
      return
    }
    let hasWritableCalendar = eventStore.calendars(for: .event)
      .contains(where: \.allowsContentModifications)
    result(probe(permission: permission, hasWritableCalendar: hasWritableCalendar))
  }

  private func handleMutation(
    operation: DeviceCalendarNativeOperation,
    arguments: Any?,
    result: @escaping FlutterResult
  ) {
    guard let request = DeviceCalendarNativeRequest(
      operation: operation,
      arguments: arguments
    ) else {
      result(failure(status: "invalid_request"))
      return
    }
    if let record = readRecord(for: request.idempotencyKey) {
      guard record.operation == operation.rawValue,
            record.inputDigest == request.inputDigest
      else {
        result(failure(status: "idempotency_conflict"))
        return
      }
      if record.status == "succeeded",
         !record.eventId.isEmpty,
         Self.isCanonicalDigest(record.receiptDigest)
      {
        result(success(
          eventId: record.eventId,
          receiptDigest: record.receiptDigest,
          replayed: true
        ))
        return
      }
    }

    let permission = permissionStatus()
    if permission == "requestable" {
      requestCalendarAccess { [weak self] granted in
        guard let self else {
          result([
            "status": "system_error",
            "deviceEventId": "",
            "receiptDigest": "",
            "replayed": false,
          ])
          return
        }
        guard granted, self.permissionStatus() == "granted" else {
          let deniedStatus = self.permissionStatus() == "restricted"
            ? "permission_restricted"
            : "permission_denied"
          result(self.failure(status: deniedStatus))
          return
        }
        self.execute(request: request, result: result)
      }
      return
    }
    guard permission == "granted" else {
      result(failure(
        status: permission == "restricted"
          ? "permission_restricted"
          : "permission_denied"
      ))
      return
    }
    execute(request: request, result: result)
  }

  private func execute(
    request: DeviceCalendarNativeRequest,
    result: @escaping FlutterResult
  ) {
    do {
      switch request.operation {
      case .create:
        try create(request: request, result: result)
      case .update:
        try update(request: request, result: result)
      case .delete:
        try delete(request: request, result: result)
      }
    } catch {
      result(failure(status: "system_error"))
    }
  }

  private func create(
    request: DeviceCalendarNativeRequest,
    result: @escaping FlutterResult
  ) throws {
    let existing = readRecord(for: request.idempotencyKey)
    if existing?.status == "pending",
       let recovered = event(matching: request),
       let identifier = recovered.eventIdentifier,
       !identifier.isEmpty
    {
      finishSuccess(
        request: request,
        eventId: identifier,
        replayed: true,
        result: result
      )
      return
    }
    guard let calendar = writableCalendar(identifier: request.calendarId) else {
      result(failure(status: "no_calendar"))
      return
    }
    guard writePending(request: request, eventId: "") else {
      result(failure(status: "system_error"))
      return
    }

    let event = EKEvent(eventStore: eventStore)
    event.calendar = calendar
    apply(request: request, to: event)
    event.url = eventMarker(for: request.idempotencyKey)
    do {
      try eventStore.save(event, span: .thisEvent, commit: true)
      guard let identifier = event.eventIdentifier, !identifier.isEmpty else {
        result(failure(status: "system_error"))
        return
      }
      guard writeSucceeded(request: request, eventId: identifier) else {
        try? eventStore.remove(event, span: .thisEvent, commit: true)
        result(failure(status: "system_error"))
        return
      }
      result(success(
        eventId: identifier,
        receiptDigest: receiptDigest(request: request, eventId: identifier),
        replayed: false
      ))
    } catch {
      try? eventStore.remove(event, span: .thisEvent, commit: true)
      throw error
    }
  }

  private func update(
    request: DeviceCalendarNativeRequest,
    result: @escaping FlutterResult
  ) throws {
    guard let event = eventStore.event(withIdentifier: request.deviceEventId) else {
      result(failure(status: "event_not_found"))
      return
    }
    if !request.calendarId.isEmpty {
      guard let calendar = writableCalendar(identifier: request.calendarId) else {
        result(failure(status: "no_calendar"))
        return
      }
      event.calendar = calendar
    }
    let replayingPending = readRecord(for: request.idempotencyKey)?.status == "pending"
    if !replayingPending,
       !writePending(request: request, eventId: request.deviceEventId)
    {
      result(failure(status: "system_error"))
      return
    }
    apply(request: request, to: event)
    try eventStore.save(event, span: .thisEvent, commit: true)
    finishSuccess(
      request: request,
      eventId: request.deviceEventId,
      replayed: replayingPending,
      result: result
    )
  }

  private func delete(
    request: DeviceCalendarNativeRequest,
    result: @escaping FlutterResult
  ) throws {
    let existing = readRecord(for: request.idempotencyKey)
    guard let event = eventStore.event(withIdentifier: request.deviceEventId) else {
      if existing?.status == "pending" {
        finishSuccess(
          request: request,
          eventId: request.deviceEventId,
          replayed: true,
          result: result
        )
      } else {
        result(failure(status: "event_not_found"))
      }
      return
    }
    guard existing?.status == "pending"
      || writePending(request: request, eventId: request.deviceEventId)
    else {
      result(failure(status: "system_error"))
      return
    }
    try eventStore.remove(event, span: .thisEvent, commit: true)
    finishSuccess(
      request: request,
      eventId: request.deviceEventId,
      replayed: existing?.status == "pending",
      result: result
    )
  }

  private func apply(
    request: DeviceCalendarNativeRequest,
    to event: EKEvent
  ) {
    event.title = request.title
    event.startDate = request.start
    event.endDate = request.end
    event.timeZone = TimeZone(identifier: request.timezone)
    event.location = request.location
    event.notes = request.notes
  }

  private func writableCalendar(identifier: String) -> EKCalendar? {
    if !identifier.isEmpty {
      guard let calendar = eventStore.calendar(withIdentifier: identifier),
            calendar.allowsContentModifications
      else {
        return nil
      }
      return calendar
    }
    guard let calendar = eventStore.defaultCalendarForNewEvents,
          calendar.allowsContentModifications
    else {
      return nil
    }
    return calendar
  }

  private func event(matching request: DeviceCalendarNativeRequest) -> EKEvent? {
    let predicate = eventStore.predicateForEvents(
      withStart: request.start.addingTimeInterval(-60),
      end: request.end.addingTimeInterval(60),
      calendars: nil
    )
    let marker = eventMarker(for: request.idempotencyKey)
    return eventStore.events(matching: predicate).first { $0.url == marker }
  }

  private func eventMarker(for idempotencyKey: String) -> URL {
    URL(string: "quwoquan://device-calendar/\(Self.sha256Hex(idempotencyKey))")!
  }

  private func finishSuccess(
    request: DeviceCalendarNativeRequest,
    eventId: String,
    replayed: Bool,
    result: @escaping FlutterResult
  ) {
    guard writeSucceeded(request: request, eventId: eventId) else {
      result(failure(status: "system_error"))
      return
    }
    result(success(
      eventId: eventId,
      receiptDigest: receiptDigest(request: request, eventId: eventId),
      replayed: replayed
    ))
  }

  private func writePending(
    request: DeviceCalendarNativeRequest,
    eventId: String
  ) -> Bool {
    writeRecord(
      DeviceCalendarMutationRecord(
        operation: request.operation.rawValue,
        inputDigest: request.inputDigest,
        eventId: eventId,
        receiptDigest: "",
        status: "pending"
      ),
      for: request.idempotencyKey
    )
  }

  private func writeSucceeded(
    request: DeviceCalendarNativeRequest,
    eventId: String
  ) -> Bool {
    writeRecord(
      DeviceCalendarMutationRecord(
        operation: request.operation.rawValue,
        inputDigest: request.inputDigest,
        eventId: eventId,
        receiptDigest: receiptDigest(request: request, eventId: eventId),
        status: "succeeded"
      ),
      for: request.idempotencyKey
    )
  }

  private func readRecord(for idempotencyKey: String) -> DeviceCalendarMutationRecord? {
    DeviceCalendarMutationRecord(
      defaults.dictionary(forKey: recordKey(idempotencyKey))
    )
  }

  private func writeRecord(
    _ record: DeviceCalendarMutationRecord,
    for idempotencyKey: String
  ) -> Bool {
    defaults.set(record.dictionary, forKey: recordKey(idempotencyKey))
    return defaults.synchronize()
  }

  private func recordKey(_ idempotencyKey: String) -> String {
    Self.recordPrefix + Self.sha256Hex(idempotencyKey)
  }

  private func receiptDigest(
    request: DeviceCalendarNativeRequest,
    eventId: String
  ) -> String {
    let material = [
      "device-calendar-receipt",
      request.operation.rawValue,
      request.idempotencyKey,
      request.inputDigest,
      eventId,
    ].joined(separator: "\n")
    return "sha256:\(Self.sha256Hex(material))"
  }

  private func permissionStatus() -> String {
    let status = EKEventStore.authorizationStatus(for: .event)
    if #available(iOS 17.0, *) {
      if status == .fullAccess {
        return "granted"
      }
      if status == .writeOnly || status == .notDetermined {
        return "requestable"
      }
      if status == .denied {
        return "denied"
      }
      return "restricted"
    }
    switch status {
    case .authorized:
      return "granted"
    case .notDetermined:
      return "requestable"
    case .denied:
      return "denied"
    case .restricted:
      return "restricted"
    @unknown default:
      return "restricted"
    }
  }

  private func requestCalendarAccess(
    completion: @escaping (Bool) -> Void
  ) {
    if #available(iOS 17.0, *) {
      eventStore.requestFullAccessToEvents { granted, _ in
        DispatchQueue.main.async { completion(granted) }
      }
    } else {
      eventStore.requestAccess(to: .event) { granted, _ in
        DispatchQueue.main.async { completion(granted) }
      }
    }
  }

  private func probe(
    permission: String,
    hasWritableCalendar: Bool
  ) -> [String: Any] {
    [
      "availability": "available",
      "permission": permission,
      "hasWritableCalendar": hasWritableCalendar,
    ]
  }

  private func success(
    eventId: String,
    receiptDigest: String,
    replayed: Bool
  ) -> [String: Any] {
    [
      "status": "succeeded",
      "deviceEventId": eventId,
      "receiptDigest": receiptDigest,
      "replayed": replayed,
    ]
  }

  private func failure(status: String) -> [String: Any] {
    [
      "status": status,
      "deviceEventId": "",
      "receiptDigest": "",
      "replayed": false,
    ]
  }

  static func sha256Hex(_ value: String) -> String {
    SHA256.hash(data: Data(value.utf8))
      .map { String(format: "%02x", $0) }
      .joined()
  }

  static func isCanonicalDigest(_ value: String) -> Bool {
    value.range(
      of: #"^sha256:[0-9a-f]{64}$"#,
      options: .regularExpression
    ) != nil
  }
}

enum DeviceCalendarNativeOperation: String {
  case create
  case update
  case delete
}

struct DeviceCalendarNativeRequest {
  init?(
    operation: DeviceCalendarNativeOperation,
    arguments rawArguments: Any?
  ) {
    guard let arguments = rawArguments as? [String: Any],
          let rawIdempotencyKey = arguments["idempotencyKey"] as? String,
          let rawInputDigest = arguments["inputDigest"] as? String
    else {
      return nil
    }
    let idempotencyKey = rawIdempotencyKey.trimmingCharacters(
      in: .whitespacesAndNewlines
    )
    let inputDigest = rawInputDigest.trimmingCharacters(
      in: .whitespacesAndNewlines
    )
    guard !idempotencyKey.isEmpty,
          idempotencyKey.count <= 128,
          AssistantDeviceActionPlugin.isCanonicalDigest(inputDigest)
    else {
      return nil
    }

    let deviceEventId = ((arguments["deviceEventId"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if operation != .create,
       deviceEventId.isEmpty || deviceEventId.count > 512
    {
      return nil
    }

    self.operation = operation
    self.idempotencyKey = idempotencyKey
    self.inputDigest = inputDigest
    self.deviceEventId = deviceEventId
    calendarId = ((arguments["calendarId"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    if calendarId.count > 512 {
      return nil
    }

    if operation == .delete {
      title = ""
      start = .distantPast
      end = .distantPast
      timezone = ""
      location = ""
      notes = ""
      return
    }

    guard let rawTitle = arguments["title"] as? String,
          let startEpochMs = arguments["startEpochMs"] as? NSNumber,
          let endEpochMs = arguments["endEpochMs"] as? NSNumber,
          let rawTimezone = arguments["timezone"] as? String
    else {
      return nil
    }
    let title = rawTitle.trimmingCharacters(in: .whitespacesAndNewlines)
    let timezone = rawTimezone.trimmingCharacters(in: .whitespacesAndNewlines)
    let startEpoch = startEpochMs.int64Value
    let endEpoch = endEpochMs.int64Value
    let location = ((arguments["location"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    let notes = ((arguments["notes"] as? String) ?? "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
    guard !title.isEmpty,
          title.count <= 200,
          startEpoch > 0,
          endEpoch > startEpoch,
          !timezone.isEmpty,
          timezone.count <= 100,
          TimeZone(identifier: timezone) != nil,
          location.count <= 500,
          notes.count <= 2000
    else {
      return nil
    }
    self.title = title
    start = Date(timeIntervalSince1970: TimeInterval(startEpoch) / 1000)
    end = Date(timeIntervalSince1970: TimeInterval(endEpoch) / 1000)
    self.timezone = timezone
    self.location = location
    self.notes = notes
  }

  let operation: DeviceCalendarNativeOperation
  let idempotencyKey: String
  let inputDigest: String
  let deviceEventId: String
  let calendarId: String
  let title: String
  let start: Date
  let end: Date
  let timezone: String
  let location: String
  let notes: String
}

struct DeviceCalendarMutationRecord {
  init(
    operation: String,
    inputDigest: String,
    eventId: String,
    receiptDigest: String,
    status: String
  ) {
    self.operation = operation
    self.inputDigest = inputDigest
    self.eventId = eventId
    self.receiptDigest = receiptDigest
    self.status = status
  }

  init?(_ raw: [String: Any]?) {
    guard let raw,
          let operation = raw["operation"] as? String,
          let inputDigest = raw["inputDigest"] as? String,
          let eventId = raw["eventId"] as? String,
          let receiptDigest = raw["receiptDigest"] as? String,
          let status = raw["status"] as? String
    else {
      return nil
    }
    self.init(
      operation: operation,
      inputDigest: inputDigest,
      eventId: eventId,
      receiptDigest: receiptDigest,
      status: status
    )
  }

  let operation: String
  let inputDigest: String
  let eventId: String
  let receiptDigest: String
  let status: String

  var dictionary: [String: String] {
    [
      "operation": operation,
      "inputDigest": inputDigest,
      "eventId": eventId,
      "receiptDigest": receiptDigest,
      "status": status,
    ]
  }
}

private final class PersonalAssistantNativeApiPlugin {
  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "getLocalContext":
      handleGetLocalContext(call: call, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func handleGetLocalContext(
    call: FlutterMethodCall,
    result: @escaping FlutterResult
  ) {
    let arguments = call.arguments as? [String: Any] ?? [:]
    let requestedFields = Set((arguments["requestedFields"] as? [String] ?? []))
    let includeLocation = requestedFields.isEmpty || requestedFields.contains("location")
    let includePermissions = requestedFields.isEmpty || requestedFields.contains("permissions")
    let includeDevice = requestedFields.isEmpty || requestedFields.contains("device")

    var payload: [String: Any] = [:]
    let locale = Locale.preferredLanguages.first ?? Locale.current.identifier
    let timezone = TimeZone.current.identifier

    if includeDevice {
      payload["device"] = [
        "os": "iOS",
        "model": UIDevice.current.model,
        "locale": locale,
        "timezone": timezone,
      ]
    }

    let authorizationStatus = CLLocationManager.authorizationStatus()
    if includePermissions {
      payload["permissions"] = [
        "location": locationPermissionLabel(for: authorizationStatus),
      ]
    }

    guard includeLocation else {
      result(payload)
      return
    }

    let manager = CLLocationManager()
    guard
      authorizationStatus == .authorizedAlways ||
      authorizationStatus == .authorizedWhenInUse
    else {
      result(payload)
      return
    }

    guard let location = manager.location else {
      result(payload)
      return
    }

    var locationPayload: [String: Any] = [
      "latitude": location.coordinate.latitude,
      "longitude": location.coordinate.longitude,
      "accuracyM": location.horizontalAccuracy,
      "source": "core_location",
    ]

    CLGeocoder().reverseGeocodeLocation(location) { placemarks, _ in
      if let placemark = placemarks?.first {
        let city = placemark.locality ?? placemark.subAdministrativeArea ?? ""
        if !city.isEmpty {
          payload["city"] = city
          payload["currentCity"] = city
          locationPayload["city"] = city
        }
        let countryCode = placemark.isoCountryCode ?? ""
        if !countryCode.isEmpty {
          locationPayload["countryCode"] = countryCode
        }
      }
      payload["locationSource"] = "core_location"
      payload["location"] = locationPayload
      payload["gpsLocation"] = locationPayload
      result(payload)
    }
  }

  private func locationPermissionLabel(for status: CLAuthorizationStatus) -> String {
    switch status {
    case .authorizedAlways, .authorizedWhenInUse:
      return "granted"
    case .denied:
      return "denied"
    case .restricted:
      return "restricted"
    case .notDetermined:
      return "not_determined"
    @unknown default:
      return "unknown"
    }
  }
}

private final class VideoEditingPlugin {
  private let queue = DispatchQueue(label: "quwoquan.video_editing", qos: .userInitiated)

  func handle(call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "extractVideoFrames":
      guard let arguments = call.arguments as? [String: Any] else {
        result(VideoEditingError.invalidArguments.flutterError)
        return
      }
      handleExtractFrames(arguments: arguments, result: result)
    case "exportVideoEdit":
      guard let arguments = call.arguments as? [String: Any] else {
        result(VideoEditingError.invalidArguments.flutterError)
        return
      }
      handleExportVideoEdit(arguments: arguments, result: result)
    case "composeOneTapMovie":
      guard let arguments = call.arguments as? [String: Any] else {
        result(VideoEditingError.invalidArguments.flutterError)
        return
      }
      handleComposeOneTapMovie(arguments: arguments, result: result)
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func handleExtractFrames(
    arguments: [String: Any],
    result: @escaping FlutterResult
  ) {
    queue.async {
      do {
        let request = try FrameExtractionRequest(arguments: arguments)
        let frames = try self.extractFrames(request: request)
        DispatchQueue.main.async {
          result(frames)
        }
      } catch let error as VideoEditingError {
        DispatchQueue.main.async {
          result(error.flutterError)
        }
      } catch {
        DispatchQueue.main.async {
          result(VideoEditingError.unknown(error.localizedDescription).flutterError)
        }
      }
    }
  }

  private func handleExportVideoEdit(
    arguments: [String: Any],
    result: @escaping FlutterResult
  ) {
    do {
      let request = try VideoEditRequest(arguments: arguments)
      let asset = AVURLAsset(url: URL(fileURLWithPath: request.sourcePath))
      let composition = try makeComposition(asset: asset, request: request)
      let outputURL = try makeOutputURL(prefix: "edited_video", fileExtension: "mp4")
      guard let exportSession = AVAssetExportSession(
        asset: composition,
        presetName: AVAssetExportPresetHighestQuality
      ) else {
        result(VideoEditingError.exportUnavailable.flutterError)
        return
      }

      let supportedTypes = exportSession.supportedFileTypes
      if supportedTypes.contains(.mp4) {
        exportSession.outputFileType = .mp4
      } else if let first = supportedTypes.first {
        exportSession.outputFileType = first
      } else {
        result(VideoEditingError.exportUnavailable.flutterError)
        return
      }
      exportSession.outputURL = outputURL
      exportSession.shouldOptimizeForNetworkUse = true

      exportSession.exportAsynchronously { [weak self] in
        guard let self else { return }
        switch exportSession.status {
        case .completed:
          self.queue.async {
            do {
              let coverPath = try self.generateCoverImage(
                sourcePath: request.sourcePath,
                timeMs: request.coverTimeMs
              )
              let payload: [String: Any] = [
                "videoPath": outputURL.path,
                "coverPath": coverPath,
                "durationMs": Int(CMTimeGetSeconds(composition.duration) * 1000),
              ]
              DispatchQueue.main.async {
                result(payload)
              }
            } catch let error as VideoEditingError {
              DispatchQueue.main.async {
                result(error.flutterError)
              }
            } catch {
              DispatchQueue.main.async {
                result(VideoEditingError.unknown(error.localizedDescription).flutterError)
              }
            }
          }
        case .failed:
          let message = exportSession.error?.localizedDescription ?? "Video export failed."
          DispatchQueue.main.async {
            result(VideoEditingError.exportFailed(message).flutterError)
          }
        case .cancelled:
          DispatchQueue.main.async {
            result(VideoEditingError.exportFailed("Video export cancelled.").flutterError)
          }
        default:
          let message = exportSession.error?.localizedDescription ?? "Video export pending."
          DispatchQueue.main.async {
            result(VideoEditingError.exportFailed(message).flutterError)
          }
        }
      }
    } catch let error as VideoEditingError {
      result(error.flutterError)
    } catch {
      result(VideoEditingError.unknown(error.localizedDescription).flutterError)
    }
  }

  private func handleComposeOneTapMovie(
    arguments: [String: Any],
    result: @escaping FlutterResult
  ) {
    queue.async {
      do {
        let request = try OneTapMovieRequest(arguments: arguments)
        let payload = try self.composeOneTapMovie(request: request)
        DispatchQueue.main.async {
          result(payload)
        }
      } catch let error as VideoEditingError {
        DispatchQueue.main.async {
          result(error.flutterError)
        }
      } catch {
        DispatchQueue.main.async {
          result(VideoEditingError.unknown(error.localizedDescription).flutterError)
        }
      }
    }
  }

  private func extractFrames(
    request: FrameExtractionRequest
  ) throws -> [[String: Any]] {
    let asset = AVURLAsset(url: URL(fileURLWithPath: request.sourcePath))
    let durationMs = max(Int(CMTimeGetSeconds(asset.duration) * 1000), 1000)
    let startMs = min(max(request.startMs, 0), durationMs - 1)
    let endMs = max(min(request.endMs, durationMs), startMs + 100)
    let count = max(request.frameCount, 1)
    let step = count == 1 ? 0 : (endMs - startMs) / max(count - 1, 1)

    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.maximumSize = CGSize(
      width: request.maxDimension,
      height: request.maxDimension
    )

    var frames: [[String: Any]] = []
    for index in 0..<count {
      let timeMs = startMs + step * index
      let time = CMTime(value: CMTimeValue(timeMs), timescale: 1000)
      let image = try generator.copyCGImage(at: time, actualTime: nil)
      let path = try writeImage(image, prefix: "frame_\(index)")
      frames.append([
        "path": path,
        "timeMs": timeMs,
      ])
    }
    return frames
  }

  private func makeComposition(
    asset: AVAsset,
    request: VideoEditRequest
  ) throws -> AVMutableComposition {
    guard let sourceVideoTrack = asset.tracks(withMediaType: .video).first else {
      throw VideoEditingError.videoTrackMissing
    }
    let composition = AVMutableComposition()
    guard let videoTrack = composition.addMutableTrack(
      withMediaType: .video,
      preferredTrackID: kCMPersistentTrackID_Invalid
    ) else {
      throw VideoEditingError.exportUnavailable
    }
    let timeRange = request.makeTimeRange(duration: asset.duration)
    try videoTrack.insertTimeRange(timeRange, of: sourceVideoTrack, at: .zero)
    videoTrack.preferredTransform = sourceVideoTrack.preferredTransform

    if !request.muted {
      for audioSourceTrack in asset.tracks(withMediaType: .audio) {
        let audioTrack = composition.addMutableTrack(
          withMediaType: .audio,
          preferredTrackID: kCMPersistentTrackID_Invalid
        )
        try audioTrack?.insertTimeRange(timeRange, of: audioSourceTrack, at: .zero)
      }
    }
    return composition
  }

  private func composeOneTapMovie(request: OneTapMovieRequest) throws -> [String: Any] {
    let outputURL = try makeOutputURL(prefix: "one_tap_movie", fileExtension: "mp4")
    let renderSize = CGSize(width: request.outputWidth, height: request.outputHeight)
    let writer = try AVAssetWriter(outputURL: outputURL, fileType: .mp4)
    let settings: [String: Any] = [
      AVVideoCodecKey: AVVideoCodecType.h264,
      AVVideoWidthKey: request.outputWidth,
      AVVideoHeightKey: request.outputHeight,
    ]
    let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
    input.expectsMediaDataInRealTime = false
    let adaptor = AVAssetWriterInputPixelBufferAdaptor(
      assetWriterInput: input,
      sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
        kCVPixelBufferWidthKey as String: request.outputWidth,
        kCVPixelBufferHeightKey as String: request.outputHeight,
        kCVPixelBufferCGImageCompatibilityKey as String: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey as String: true,
      ]
    )
    guard writer.canAdd(input) else {
      throw VideoEditingError.exportUnavailable
    }
    writer.add(input)
    guard writer.startWriting() else {
      throw VideoEditingError.exportFailed(writer.error?.localizedDescription ?? "Unable to start writer.")
    }
    writer.startSession(atSourceTime: .zero)

    let frameDuration = CMTime(value: 1, timescale: 30)
    for (index, path) in request.imagePaths.enumerated() {
      guard let image = UIImage(contentsOfFile: path) else {
        throw VideoEditingError.imageReadFailed(path)
      }
      let start = CMTime(value: CMTimeValue(index * request.secondsPerImage), timescale: 1)
      try appendImageFrame(
        image,
        renderSize: renderSize,
        at: start,
        input: input,
        adaptor: adaptor
      )
      let next = CMTime(
        value: CMTimeValue((index + 1) * request.secondsPerImage),
        timescale: 1
      )
      let end = CMTimeSubtract(next, frameDuration)
      if CMTimeCompare(end, start) > 0 {
        try appendImageFrame(
          image,
          renderSize: renderSize,
          at: end,
          input: input,
          adaptor: adaptor
        )
      }
    }

    input.markAsFinished()
    let semaphore = DispatchSemaphore(value: 0)
    writer.finishWriting {
      semaphore.signal()
    }
    semaphore.wait()
    guard writer.status == .completed else {
      throw VideoEditingError.exportFailed(
        writer.error?.localizedDescription ?? "One-tap movie export failed."
      )
    }
    let coverPath = try writeUIImage(
      UIImage(contentsOfFile: request.imagePaths[0]) ?? UIImage(),
      prefix: "one_tap_movie_cover"
    )
    return [
      "videoPath": outputURL.path,
      "coverPath": coverPath,
      "durationMs": request.imagePaths.count * request.secondsPerImage * 1000,
    ]
  }

  private func appendImageFrame(
    _ image: UIImage,
    renderSize: CGSize,
    at time: CMTime,
    input: AVAssetWriterInput,
    adaptor: AVAssetWriterInputPixelBufferAdaptor
  ) throws {
    while !input.isReadyForMoreMediaData {
      Thread.sleep(forTimeInterval: 0.01)
    }
    guard let buffer = makePixelBuffer(from: image, renderSize: renderSize) else {
      throw VideoEditingError.pixelBufferFailed
    }
    guard adaptor.append(buffer, withPresentationTime: time) else {
      throw VideoEditingError.exportFailed("Unable to append one-tap movie frame.")
    }
  }

  private func makePixelBuffer(from image: UIImage, renderSize: CGSize) -> CVPixelBuffer? {
    var pixelBuffer: CVPixelBuffer?
    let status = CVPixelBufferCreate(
      kCFAllocatorDefault,
      Int(renderSize.width),
      Int(renderSize.height),
      kCVPixelFormatType_32BGRA,
      [
        kCVPixelBufferCGImageCompatibilityKey: true,
        kCVPixelBufferCGBitmapContextCompatibilityKey: true,
      ] as CFDictionary,
      &pixelBuffer
    )
    guard status == kCVReturnSuccess, let buffer = pixelBuffer else {
      return nil
    }
    CVPixelBufferLockBaseAddress(buffer, [])
    defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
    guard
      let context = CGContext(
        data: CVPixelBufferGetBaseAddress(buffer),
        width: Int(renderSize.width),
        height: Int(renderSize.height),
        bitsPerComponent: 8,
        bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue |
          CGBitmapInfo.byteOrder32Little.rawValue
      )
    else {
      return nil
    }
    UIGraphicsPushContext(context)
    UIColor.black.setFill()
    UIRectFill(CGRect(origin: .zero, size: renderSize))
    image.draw(in: aspectFitRect(imageSize: image.size, canvasSize: renderSize))
    UIGraphicsPopContext()
    return buffer
  }

  private func aspectFitRect(imageSize: CGSize, canvasSize: CGSize) -> CGRect {
    guard imageSize.width > 0 && imageSize.height > 0 else {
      return CGRect(origin: .zero, size: canvasSize)
    }
    let scale = min(canvasSize.width / imageSize.width, canvasSize.height / imageSize.height)
    let width = imageSize.width * scale
    let height = imageSize.height * scale
    return CGRect(
      x: (canvasSize.width - width) / 2,
      y: (canvasSize.height - height) / 2,
      width: width,
      height: height
    )
  }

  private func generateCoverImage(sourcePath: String, timeMs: Int) throws -> String {
    let asset = AVURLAsset(url: URL(fileURLWithPath: sourcePath))
    let durationMs = max(Int(CMTimeGetSeconds(asset.duration) * 1000), 1000)
    let clampedTimeMs = min(max(timeMs, 0), durationMs - 1)
    let generator = AVAssetImageGenerator(asset: asset)
    generator.appliesPreferredTrackTransform = true
    generator.maximumSize = CGSize(width: 720, height: 720)
    let time = CMTime(value: CMTimeValue(clampedTimeMs), timescale: 1000)
    let image = try generator.copyCGImage(at: time, actualTime: nil)
    return try writeImage(image, prefix: "cover")
  }

  private func writeImage(_ image: CGImage, prefix: String) throws -> String {
    return try writeUIImage(UIImage(cgImage: image), prefix: prefix)
  }

  private func writeUIImage(_ image: UIImage, prefix: String) throws -> String {
    let url = try makeOutputURL(prefix: prefix, fileExtension: "jpg")
    guard let data = image.jpegData(compressionQuality: 0.9) else {
      throw VideoEditingError.imageWriteFailed
    }
    try data.write(to: url, options: .atomic)
    return url.path
  }

  private func makeOutputURL(prefix: String, fileExtension: String) throws -> URL {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent("quwoquan_video_editing", isDirectory: true)
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true,
      attributes: nil
    )
    let fileName = "\(prefix)_\(UUID().uuidString).\(fileExtension)"
    let outputURL = directory.appendingPathComponent(fileName)
    if FileManager.default.fileExists(atPath: outputURL.path) {
      try FileManager.default.removeItem(at: outputURL)
    }
    return outputURL
  }
}

private struct FrameExtractionRequest {
  init(arguments: [String: Any]) throws {
    guard let sourcePath = arguments["sourcePath"] as? String, !sourcePath.isEmpty else {
      throw VideoEditingError.invalidArguments
    }
    self.sourcePath = sourcePath
    self.startMs = arguments["startMs"] as? Int ?? 0
    self.endMs = arguments["endMs"] as? Int ?? 0
    self.frameCount = arguments["frameCount"] as? Int ?? 12
    self.maxDimension = arguments["maxDimension"] as? Int ?? 360
  }

  let sourcePath: String
  let startMs: Int
  let endMs: Int
  let frameCount: Int
  let maxDimension: Int
}

private struct VideoEditRequest {
  init(arguments: [String: Any]) throws {
    guard let sourcePath = arguments["sourcePath"] as? String, !sourcePath.isEmpty else {
      throw VideoEditingError.invalidArguments
    }
    self.sourcePath = sourcePath
    self.trimStartMs = arguments["trimStartMs"] as? Int ?? 0
    self.trimEndMs = arguments["trimEndMs"] as? Int ?? 0
    self.muted = arguments["muted"] as? Bool ?? false
    self.coverTimeMs = arguments["coverTimeMs"] as? Int ?? 0
  }

  let sourcePath: String
  let trimStartMs: Int
  let trimEndMs: Int
  let muted: Bool
  let coverTimeMs: Int

  var trimmedDurationMs: Int {
    let end = trimEndMs > trimStartMs ? trimEndMs : trimStartMs
    return max(end - trimStartMs, 0)
  }

  func makeTimeRange(duration: CMTime) -> CMTimeRange {
    let totalMs = max(Int(CMTimeGetSeconds(duration) * 1000), 1000)
    let start = min(max(trimStartMs, 0), totalMs - 1)
    let endCandidate = trimEndMs > 0 ? trimEndMs : totalMs
    let end = max(min(endCandidate, totalMs), start + 100)
    let startTime = CMTime(value: CMTimeValue(start), timescale: 1000)
    let endTime = CMTime(value: CMTimeValue(end), timescale: 1000)
    return CMTimeRange(start: startTime, end: endTime)
  }
}

private struct OneTapMovieRequest {
  init(arguments: [String: Any]) throws {
    let rawImagePaths = arguments["imagePaths"] as? [String] ?? []
    let imagePaths = rawImagePaths
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { !$0.isEmpty }
    guard !imagePaths.isEmpty else {
      throw VideoEditingError.invalidArguments
    }
    self.imagePaths = imagePaths
    self.secondsPerImage = max(arguments["secondsPerImage"] as? Int ?? 3, 1)
    self.outputWidth = max(arguments["outputWidth"] as? Int ?? 1080, 320)
    self.outputHeight = max(arguments["outputHeight"] as? Int ?? 1920, 320)
  }

  let imagePaths: [String]
  let secondsPerImage: Int
  let outputWidth: Int
  let outputHeight: Int
}

private enum VideoEditingError: Error {
  case invalidArguments
  case videoTrackMissing
  case exportUnavailable
  case exportFailed(String)
  case imageReadFailed(String)
  case imageWriteFailed
  case pixelBufferFailed
  case unknown(String)

  var flutterError: FlutterError {
    switch self {
    case .invalidArguments:
      return FlutterError(
        code: "video_edit_invalid_arguments",
        message: "Invalid video editing arguments.",
        details: nil
      )
    case .videoTrackMissing:
      return FlutterError(
        code: "video_edit_missing_track",
        message: "Video track missing.",
        details: nil
      )
    case .exportUnavailable:
      return FlutterError(
        code: "video_edit_export_unavailable",
        message: "Unable to create export session.",
        details: nil
      )
    case let .exportFailed(message):
      return FlutterError(
        code: "video_edit_export_failed",
        message: message,
        details: nil
      )
    case let .imageReadFailed(path):
      return FlutterError(
        code: "video_edit_image_read_failed",
        message: "Unable to read image: \(path)",
        details: nil
      )
    case .imageWriteFailed:
      return FlutterError(
        code: "video_edit_image_write_failed",
        message: "Unable to write thumbnail image.",
        details: nil
      )
    case .pixelBufferFailed:
      return FlutterError(
        code: "video_edit_pixel_buffer_failed",
        message: "Unable to render one-tap movie frame.",
        details: nil
      )
    case let .unknown(message):
      return FlutterError(
        code: "video_edit_unknown",
        message: message,
        details: nil
      )
    }
  }
}
