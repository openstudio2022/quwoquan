// Runtime config 的原生供给栈：trust 校验、package 读取、activation 编排与
// Flutter channel 注册。
//
// 本文件被生产 Runner 与 Patrol UAT test host 两个 Xcode target 共同编译，
// 是两者取得已验签 package 的唯一实现。test host 自己执行 `runQuwoquanApp`，
// 与生产 App 一样在启动首步就要拿到 package；若让 test host 复制第二份读取面，
// 两条启动路径的行为等价性就失去了机械保证。因此这里只有一份源码，
// test host 工程以相对路径引用同一文件，而不是维护副本。

import CryptoKit
import CoreFoundation
import Foundation

let nativeRuntimePackageFileName = "runtime-config-package.json"
let nativeRuntimeTrustFileName = "runtime-config-trust.json"
let nativeRuntimeActivationRequestFileName = "runtime-config-activation-request.json"
let nativeRuntimeActivationReceiptFileName = "runtime-config-activation-receipt.json"
let nativeRuntimeActiveReceiptFileName = "runtime-config-active-receipt.json"
// Debug-nonprod 构建期自供给（REQ-003 build_time_self_supply）随制品嵌入的激活请求。
let nativeRuntimeSelfSupplyRequestFileName = "runtime-config-self-supply-request.json"
let nativeRuntimeSelfSupplyMode = "build_time_self_supply"
let nativeRuntimeActivationRequestDigestArgument =
  "--qwq-runtime-config-activation-request-digest"
let nativeRuntimeConfigDirectory = "qwq_runtime"
let nativeRuntimeMigrationHistoryDirectory = "migration-history"
let nativeRuntimePreviousLayoutPackageArchiveFileName = "historical-package.json"
let nativeRuntimePreviousLayoutReceiptArchiveFileName = "historical-active-receipt.json"
let nativeRuntimePreviousLayoutAuditArchiveFileName = "migration-audit.json"
let nativeRuntimePreviousLayoutAuditSchema =
  "quwoquan.ios.runtime_config_previousLayout_migration_audit.v1"
let nativeRuntimeConfigMaximumBytes = 1024 * 1024

func nativeSHA256Identity(_ data: Data) -> String {
  "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

func nativeRuntimeConfigInternalFailure(
  context: String,
  error: Error
) -> NativeRuntimeConfigReadError {
  NSLog(
    "QWQStartup ios_runtime_config_internal_failure context=%@ errorType=%@",
    context,
    String(reflecting: type(of: error))
  )
  return .internalFailure
}

enum NativeRuntimeConfigReadError: Error {
  case trustMissing
  case trustPathInvalid
  case trustReadFailed
  case trustEmpty
  case trustTooLarge
  case trustMalformed
  case trustKeyringInvalid
  case packageMissing
  case packagePathInvalid
  case packageReadFailed
  case packageEmpty
  case packageTooLarge
  case packageMalformed
  case schemaMismatch
  case profileMismatch
  case targetMismatch
  case policyMismatch
  case endpointInvalid
  case runtimeValuesInvalid
  case contentSourceMismatch
  case networkForbidden
  case sourceIdentityInvalid
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
  case activationRequestReadFailed
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
  case digestUnavailable
  case internalFailure

  var flutterCode: String {
    let code: String
    switch self {
    case .trustMissing: code = "runtime_config_trust_missing"
    case .trustPathInvalid: code = "runtime_config_trust_path_invalid"
    case .trustReadFailed: code = "runtime_config_trust_read_failed"
    case .trustEmpty: code = "runtime_config_trust_empty"
    case .trustTooLarge: code = "runtime_config_trust_too_large"
    case .trustMalformed: code = "runtime_config_trust_malformed"
    case .trustKeyringInvalid: code = "runtime_config_trust_keyring_invalid"
    case .packageMissing: code = "runtime_config_package_missing"
    case .packagePathInvalid: code = "runtime_config_package_path_invalid"
    case .packageReadFailed: code = "runtime_config_package_read_failed"
    case .packageEmpty: code = "runtime_config_package_empty"
    case .packageTooLarge: code = "runtime_config_package_too_large"
    case .packageMalformed: code = "runtime_config_package_malformed"
    case .schemaMismatch: code = "runtime_config_schema_mismatch"
    case .profileMismatch: code = "runtime_config_profile_mismatch"
    case .targetMismatch: code = "runtime_config_target_mismatch"
    case .policyMismatch: code = "runtime_config_launch_policy_mismatch"
    case .endpointInvalid: code = "runtime_config_endpoint_invalid"
    case .runtimeValuesInvalid: code = "runtime_config_runtime_values_invalid"
    case .contentSourceMismatch: code = "runtime_config_content_source_mismatch"
    case .networkForbidden: code = "runtime_config_network_forbidden"
    case .sourceIdentityInvalid: code = "runtime_config_source_identity_invalid"
    case .algorithmMismatch: code = "runtime_config_signature_algorithm_mismatch"
    case .keyringMismatch: code = "runtime_config_keyring_mismatch"
    case .signatureKeyUntrusted: code = "runtime_config_signature_key_untrusted"
    case .payloadDigestMismatch: code = "runtime_config_payload_digest_mismatch"
    case .packageDigestMismatch: code = "runtime_config_package_digest_mismatch"
    case .trustDigestMismatch: code = "runtime_config_trust_digest_mismatch"
    case .signatureInvalid: code = "runtime_config_signature_invalid"
    case .freshnessInvalid: code = "runtime_config_freshness_invalid"
    case .activeDigestConflict: code = "runtime_config_active_digest_conflict"
    case .activationWriteFailed: code = "runtime_config_activation_write_failed"
    case .activationReadbackFailed: code = "runtime_config_activation_readback_failed"
    case .activationRollbackFailed: code = "runtime_config_activation_rollback_failed"
    case .activationRequiresColdStart:
      code = "runtime_config_activation_requires_cold_start"
    case .activationRequestMissing: code = "runtime_config_activation_request_missing"
    case .activationRequestReadFailed:
      code = "runtime_config_activation_request_read_failed"
    case .activationRequestMalformed: code = "runtime_config_activation_request_malformed"
    case .activationRequestDigestInvalid:
      code = "runtime_config_activation_request_digest_invalid"
    case .activationRequestDigestMismatch:
      code = "runtime_config_activation_request_digest_mismatch"
    case .effectiveManifestMalformed: code = "runtime_config_effective_manifest_malformed"
    case .effectiveManifestDigestMismatch:
      code = "runtime_config_effective_manifest_digest_mismatch"
    case .activationIdentityMismatch:
      code = "runtime_config_activation_identity_mismatch"
    case .activationReceiptMissing: code = "runtime_config_activation_receipt_missing"
    case .activationReceiptReadFailed:
      code = "runtime_config_activation_receipt_read_failed"
    case .activationReceiptMalformed:
      code = "runtime_config_activation_receipt_malformed"
    case .activationReceiptMismatch:
      code = "runtime_config_activation_receipt_mismatch"
    case .activationReceiptWriteFailed:
      code = "runtime_config_activation_receipt_write_failed"
    case .digestUnavailable: code = "runtime_config_digest_unavailable"
    case .internalFailure: code = "runtime_config_internal_failure"
    }
    // 闭集由 metadata codegen 拥有；本地 enum 仅保留 Swift 控制流类型，任何未登记
    // selector 都在开发期立即暴露，不能静默成为第二套错误码注册表。
    precondition(
      AppLaunchContract.runtimeConfigErrorCodes[code] != nil,
      "runtime config error code is absent from AppLaunchContract: \(code)"
    )
    return code
  }
}

struct NativeRuntimeConfigTrustProjection {
  let artifactTrustEnvelope: [String: Any]
  let trustEnvelopeDigest: String
  let trustedPublicKeys: [String: String]
}

struct NativeRuntimeConfigActiveProjection {
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

enum NativeRuntimeConfigReadState {
  case present(NativeRuntimeConfigActiveProjection)
  case absent(NativeRuntimeConfigTrustProjection)
  case failure(NativeRuntimeConfigReadError)
}

struct NativeRuntimeConfigActivationResult {
  let packageDigest: String
  let trustEnvelopeDigest: String
  let previousActiveDigest: String
}

enum NativeRuntimeConfigStore {
  private static let packageFields = Set(
    AppLaunchContract.runtimeConfigPackageRequiredFields
  )
  private static let runtimeFields = Set(
    AppLaunchContract.runtimeConfigPackageRuntimeRequiredFields
  )
  // 唯一可迁移的历史形状：现行 Alpha 离线文档的直接 predecessor，
  // 只比当前闭集少 rehearsalSpace。不得由普通 reader 或 self-supply 使用。
  static let previousLayoutOfflinePredecessorFields = Set(
    AppLaunchContract.offlineBootstrapDocumentRequiredFields.filter {
      $0 != "rehearsalSpace"
    }
  )
  private static let websocketRuntimeFields = Set([
    "realtimeBaseUrl",
    "rtcMediaConnectionUrl",
  ])
  private static let maximumLifetime = TimeInterval(
    AppLaunchContract.runtimeConfigPackageMaxLifetimeSeconds
  )
  private static let maximumFutureSkew = TimeInterval(
    AppLaunchContract.runtimeConfigPackageMaxFutureSkewSeconds
  )
  private static let writeQueue = DispatchQueue(label: "quwoquan.runtime.config.activation")

  static func readActivePackage() -> NativeRuntimeConfigReadState {
    loadActivePackage()
  }

  static var networkAccessAllowed: Bool {
    guard case .present(let active) = readActivePackage() else { return false }
    return AppLaunchContract.runtimeDocumentContentSources[active.package["schema"] as? String ?? ""] == "remote"
  }

  static func loadActivePackage(
    allowStaleIdentity: Bool = false
  ) -> NativeRuntimeConfigReadState {
    do {
      let trust = try loadTrustEnvelope()
      guard let packageURL = try runtimePackageURL(createDirectory: false) else {
        return .absent(trust)
      }
      let storedPackageData = try readData(
        url: packageURL,
        pathError: .packagePathInvalid,
        readError: .packageReadFailed,
        emptyError: .packageEmpty,
        sizeError: .packageTooLarge,
      )
      let package = try decodeDocument(storedPackageData, malformedError: .packageMalformed)
      let canonicalPackageData = try canonicalJSONData(package)
      let active = try validatePackage(
        package,
        packageData: canonicalPackageData,
        trust: trust,
        expectedPackageDigest: nil,
        allowStaleIdentity: allowStaleIdentity
      )
      return .present(active)
    } catch let error as NativeRuntimeConfigReadError {
      return .failure(error)
    } catch {
      return .failure(nativeRuntimeConfigInternalFailure(
        context: "load_active_package",
        error: error
      ))
    }
  }

  // 激活流程读取 CAS 前值专用：时间窗过期的旧包必须仍可被替换，不得死锁激活。
  static func readActivePackageIdentity() -> NativeRuntimeConfigReadState {
    loadActivePackage(allowStaleIdentity: true)
  }

  static func readRuntimeConfig() throws -> [String: Any] {
    let identity = try NativeRuntimeConfigActivationCoordinator.readVerifiedIdentity()
    switch readActivePackage() {
    case .present(let active):
      var envelope = active.flutterEnvelope
      envelope["runtimeConfigPackageDigest"] = active.packageDigest
      envelope["runtimeConfigTrustEnvelopeDigest"] = active.trustEnvelopeDigest
      envelope["effectiveLaunchManifestDigest"] = identity.effectiveLaunchManifestDigest
      envelope["launchProvenance"] = identity.launchProvenance
      envelope["runtimeConfigSupplyMode"] = identity.runtimeConfigSupplyMode
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
    allowPreviousLayoutOfflinePredecessor: Bool = false,
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
      // CAS 前值只需要身份：时间窗过期的旧包必须仍可被替换，不得死锁激活。
      let previousLayoutPredecessor = allowPreviousLayoutOfflinePredecessor
        ? try loadPreviousLayoutOfflinePredecessorArchive()
        : nil
      let currentDigest: String
      if let previousLayoutPredecessor {
        currentDigest = previousLayoutPredecessor.active.packageDigest
      } else {
        switch loadActivePackage(allowStaleIdentity: true) {
        case .present(let active):
          currentDigest = active.packageDigest
        case .absent:
          currentDigest = ""
        case .failure(let error):
          throw error
        }
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
      if let previousLayoutPredecessor {
        try archivePreviousLayoutMigrationHistory(
          packageData: previousLayoutPredecessor.packageData,
          receiptData: previousLayoutPredecessor.receiptData,
          packageDigest: previousLayoutPredecessor.active.packageDigest,
          baseDirectory: try runtimeConfigDirectoryURL(createDirectory: true)
        )
      }
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
        let normalizedError = (error as? NativeRuntimeConfigReadError)
          ?? nativeRuntimeConfigInternalFailure(
            context: "activate_runtime_package",
            error: error
          )
        try restorePreviousActivePackage(
          previousActivePackage,
          originalError: normalizedError
        )
        throw normalizedError
      }
    }
  }

  static func loadTrustEnvelope() throws -> NativeRuntimeConfigTrustProjection {
    guard let trustURL = bundledTrustURL() else {
      throw NativeRuntimeConfigReadError.trustMissing
    }
    let trustData = try readData(
      url: trustURL,
      pathError: .trustPathInvalid,
      readError: .trustReadFailed,
      emptyError: .trustEmpty,
      sizeError: .trustTooLarge,
    )
    let trust = try decodeDocument(trustData, malformedError: .trustMalformed)
    guard Set(trust.keys) == Set(AppLaunchContract.runtimeConfigTrustEnvelopeRequiredFields),
      trust["schema"] as? String
        == AppLaunchContract.schemaValues["runtime_config_trust_envelope"],
      trust["signatureAlgorithm"] as? String
        == AppLaunchContract.runtimeConfigPackageSignatureAlgorithm,
      let buildProfile = nonEmptyString(trust["buildProfile"]),
      AppLaunchContract.buildProfileEnvironments[buildProfile] != nil
    else {
      throw NativeRuntimeConfigReadError.trustMalformed
    }
    let trustedPublicKeys = try normalizedKeyring(
      trust["trustedPublicKeys"],
      invalidError: .trustKeyringInvalid
    )
    return NativeRuntimeConfigTrustProjection(
      artifactTrustEnvelope: trust,
      trustEnvelopeDigest: nativeSHA256Identity(try canonicalJSONData(trust)),
      trustedPublicKeys: trustedPublicKeys
    )
  }

  static func validatePackage(
    _ package: [String: Any],
    packageData: Data,
    trust: NativeRuntimeConfigTrustProjection,
    expectedPackageDigest: String?,
    allowStaleIdentity: Bool = false,
    requiredFields: Set<String>? = nil
  ) throws -> NativeRuntimeConfigActiveProjection {
    let schema = package["schema"] as? String ?? ""
    let offline = schema == AppLaunchContract.schemaValues["offline_bootstrap_document"]
    let fields = requiredFields
      ?? (offline ? Set(AppLaunchContract.offlineBootstrapDocumentRequiredFields) : packageFields)
    guard requiredFields == nil || offline,
          Set(package.keys) == fields,
          offline || schema == AppLaunchContract.schemaValues["runtime_config_package"]
    else {
      throw NativeRuntimeConfigReadError.schemaMismatch
    }
    guard package["signatureAlgorithm"] as? String
            == AppLaunchContract.runtimeConfigPackageSignatureAlgorithm,
          trust.artifactTrustEnvelope["signatureAlgorithm"] as? String
            == AppLaunchContract.runtimeConfigPackageSignatureAlgorithm
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
          AppLaunchContract.targetEnvironment[target] == environment
    else {
      throw NativeRuntimeConfigReadError.targetMismatch
    }
    let expectedPolicy = AppLaunchContract.buildProfileLaunchPolicies[profile]
    let allowedEnvironments = Set(
      AppLaunchContract.buildProfileEnvironments[profile] ?? []
    )
    guard allowedEnvironments.contains(environment),
          package["launchPolicy"] as? String == expectedPolicy,
          expectedPolicy != nil
    else {
      throw NativeRuntimeConfigReadError.policyMismatch
    }
    let source = AppLaunchContract.runtimeDocumentContentSources[schema]
    // 只识别显式 activation 的 CAS 前值；退役 Alpha 在线包仍不可消费或作为新候选。
    let retiredAlphaIdentity = allowStaleIdentity && !offline && environment == "alpha" && target == "alpha-local"
    guard source != nil, retiredAlphaIdentity || source == AppLaunchContract.contentSourcePolicy[environment],
          !offline || (package["contentSource"] as? String == source && profile == "nonprod"
            && target == "alpha-local"
            && package["trustEnvelopeDigest"] as? String == trust.trustEnvelopeDigest)
    else { throw NativeRuntimeConfigReadError.contentSourceMismatch }
    _ = try validateRuntimeValues(package["runtime"], environment: environment, offline: offline)
    let packageKeyring = try normalizedKeyring(
      package["trustedPublicKeys"],
      invalidError: .keyringMismatch
    )
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
    try validateSourceIdentity(package)
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
    if !offline { try validateFreshness(package, allowStaleIdentity: allowStaleIdentity) }
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



  // allowStaleIdentity 只供激活流程读取 CAS 前值：豁免 expiresAt 时间窗，
  // 结构/生命周期上限/未来偏移校验保留；消费路径必须走严格默认值
  //（environment-topology-and-packaging spec：过期即死锁的实现是违约）。
  static func validateFreshness(
    _ package: [String: Any],
    allowStaleIdentity: Bool = false,
    now: Date = Date()
  ) throws {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let fallback = ISO8601DateFormatter()
    guard let issuedRaw = nonEmptyString(package["issuedAt"]),
          let expiresRaw = nonEmptyString(package["expiresAt"]),
          let issuedAt = formatter.date(from: issuedRaw) ?? fallback.date(from: issuedRaw),
          let expiresAt = formatter.date(from: expiresRaw) ?? fallback.date(from: expiresRaw),
          expiresAt > issuedAt,
          expiresAt.timeIntervalSince(issuedAt) <= maximumLifetime,
          issuedAt.timeIntervalSince(now) <= maximumFutureSkew
    else {
      throw NativeRuntimeConfigReadError.freshnessInvalid
    }
    guard allowStaleIdentity || expiresAt > now else {
      throw NativeRuntimeConfigReadError.freshnessInvalid
    }
  }

  static func validateRuntimeValues(
    _ value: Any?,
    environment: String,
    offline: Bool = false
  ) throws -> [String: Any] {
    let fields = offline ? Set(AppLaunchContract.offlineBootstrapRuntimeRequiredFields) : runtimeFields
    guard let runtime = value as? [String: Any],
          Set(runtime.keys) == fields,
          runtime["appRuntimeEnv"] as? String == environment
    else {
      throw NativeRuntimeConfigReadError.runtimeValuesInvalid
    }
    for key in fields {
      guard let raw = runtime[key] as? String,
            !raw.isEmpty,
            raw == raw.trimmingCharacters(in: .whitespacesAndNewlines)
      else {
        throw NativeRuntimeConfigReadError.runtimeValuesInvalid
      }
      if key != "appRuntimeEnv" {
        try validateEndpoint(key: key, raw: raw)
      }
    }
    return runtime
  }

  static func validateSourceIdentity(_ package: [String: Any]) throws {
    guard let sourceGitSHA = package["sourceGitSha"] as? String,
          sourceGitSHA.range(of: "^[0-9a-f]{40}$", options: .regularExpression) != nil,
          let sourceTreeDigest = package["sourceTreeDigest"] as? String,
          sourceTreeDigest.range(
            of: "^(?:sha1:[0-9a-f]{40}|sha256:[0-9a-f]{64})$",
            options: .regularExpression
          ) != nil
    else {
      throw NativeRuntimeConfigReadError.sourceIdentityInvalid
    }
  }

  private static func validateEndpoint(key: String, raw: String) throws {
    guard let components = URLComponents(string: raw),
          components.scheme?.lowercased()
            == (websocketRuntimeFields.contains(key) ? "wss" : "https"),
          let host = components.host,
          !host.isEmpty,
          components.user == nil,
          components.password == nil,
          components.percentEncodedQuery == nil,
          components.fragment == nil
    else {
      throw NativeRuntimeConfigReadError.endpointInvalid
    }
  }

  static func normalizedKeyring(
    _ value: Any?,
    invalidError: NativeRuntimeConfigReadError
  ) throws -> [String: String] {
    guard let rawKeyring = value as? [String: Any], !rawKeyring.isEmpty else {
      throw invalidError
    }
    var keyring: [String: String] = [:]
    let firstAllowed = CharacterSet(
      charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    )
    let allowed = CharacterSet(
      charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-"
    )
    for (keyID, rawValue) in rawKeyring {
      guard !keyID.isEmpty,
            keyID.count <= 128,
            keyID.unicodeScalars.first.map({ firstAllowed.contains($0) }) == true,
            keyID.unicodeScalars.allSatisfy({ allowed.contains($0) }),
            let encoded = nonEmptyString(rawValue),
            let decoded = Data(base64Encoded: encoded),
            decoded.count == 32,
            decoded.base64EncodedString() == encoded
      else {
        throw invalidError
      }
      keyring[keyID] = encoded
    }
    return keyring
  }

  static func canonicalJSONData(_ document: [String: Any]) throws -> Data {
    guard JSONSerialization.isValidJSONObject(document) else {
      throw NativeRuntimeConfigReadError.packageMalformed
    }
    do {
      return try NativeRuntimeCanonicalJSON.data(document)
    } catch {
      throw NativeRuntimeConfigReadError.packageMalformed
    }
  }

  static func decodeDocument(
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

  static func readData(
    url: URL,
    pathError: NativeRuntimeConfigReadError,
    readError: NativeRuntimeConfigReadError,
    emptyError: NativeRuntimeConfigReadError,
    sizeError: NativeRuntimeConfigReadError,
    load: (URL) throws -> Data = { url in
      try Data(contentsOf: url, options: [.mappedIfSafe])
    }
  ) throws -> Data {
    let values: URLResourceValues
    do {
      values = try url.resourceValues(forKeys: [
        .isRegularFileKey,
        .isSymbolicLinkKey,
        .fileSizeKey,
      ])
    } catch {
      throw readError
    }
    guard values.isRegularFile == true, values.isSymbolicLink != true else {
      throw pathError
    }
    guard let size = values.fileSize else {
      throw readError
    }
    guard size > 0 else {
      throw emptyError
    }
    guard size <= nativeRuntimeConfigMaximumBytes else {
      throw sizeError
    }
    let data: Data
    do {
      data = try load(url)
    } catch {
      throw readError
    }
    guard !data.isEmpty else {
      throw emptyError
    }
    guard data.count <= nativeRuntimeConfigMaximumBytes else {
      throw sizeError
    }
    return data
  }

  private static func readCurrentActivePackageData() throws -> Data? {
    guard let packageURL = try runtimePackageURL(createDirectory: false) else {
      return nil
    }
    return try readData(
      url: packageURL,
      pathError: .packagePathInvalid,
      readError: .packageReadFailed,
      emptyError: .packageEmpty,
      sizeError: .packageTooLarge,
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

  static func runtimePackageURL(createDirectory: Bool) throws -> URL? {
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
    let directory = try runtimeConfigDirectoryURL(
      createDirectory: createDirectory,
      supportRoot: supportRoot
    )
    let packageURL = directory
      .appendingPathComponent(nativeRuntimePackageFileName, isDirectory: false)
      .standardizedFileURL
    guard packageURL.path.hasPrefix(directory.path + "/") else {
      throw NativeRuntimeConfigReadError.packagePathInvalid
    }
    return packageURL
  }

  static func runtimeConfigDirectoryURL(
    createDirectory: Bool,
    supportRoot providedSupportRoot: URL? = nil
  ) throws -> URL {
    let fileManager = FileManager.default
    let supportRoot: URL
    if let providedSupportRoot {
      supportRoot = providedSupportRoot
    } else {
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
    return directory
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

  static func synchronizeDirectory(_ directory: URL) throws {
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

  static func digestIdentity(_ value: Any?) -> String? {
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
    return trimmed.isEmpty || trimmed != string ? nil : string
  }
}
