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
import Flutter
import Foundation

private let nativeRuntimePackageFileName = "runtime-config-package.json"
private let nativeRuntimeTrustFileName = "runtime-config-trust.json"
private let nativeRuntimeActivationRequestFileName = "runtime-config-activation-request.json"
private let nativeRuntimeActivationReceiptFileName = "runtime-config-activation-receipt.json"
private let nativeRuntimeActiveReceiptFileName = "runtime-config-active-receipt.json"
private let nativeRuntimeActivationRequestDigestArgument =
  "--qwq-runtime-config-activation-request-digest"
private let nativeRuntimeConfigDirectory = "qwq_runtime"
private let nativeRuntimeConfigMaximumBytes = 1024 * 1024

private func nativeSHA256Identity(_ data: Data) -> String {
  "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func nativeRuntimeConfigInternalFailure(
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

  private static func loadActivePackage(
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
      let currentState = loadActivePackage(allowStaleIdentity: true)
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

  private static func loadTrustEnvelope() throws -> NativeRuntimeConfigTrustProjection {
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

  private static func validatePackage(
    _ package: [String: Any],
    packageData: Data,
    trust: NativeRuntimeConfigTrustProjection,
    expectedPackageDigest: String?,
    allowStaleIdentity: Bool = false
  ) throws -> NativeRuntimeConfigActiveProjection {
    guard Set(package.keys) == packageFields,
          package["schema"] as? String
            == AppLaunchContract.schemaValues["runtime_config_package"]
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
    _ = try validateRuntimeValues(package["runtime"], environment: environment)
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
    try validateFreshness(package, allowStaleIdentity: allowStaleIdentity)
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
    environment: String
  ) throws -> [String: Any] {
    guard let runtime = value as? [String: Any],
          Set(runtime.keys) == runtimeFields,
          runtime["appRuntimeEnv"] as? String == environment
    else {
      throw NativeRuntimeConfigReadError.runtimeValuesInvalid
    }
    for key in runtimeFields {
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
    return trimmed.isEmpty || trimmed != string ? nil : string
  }
}

struct NativeRuntimeConfigActivationIdentity {
  let packageDigest: String
  let trustEnvelopeDigest: String
  let effectiveLaunchManifestDigest: String
  let launchProvenance: String
  let runtimeConfigSupplyMode: String
}

private struct NativeRuntimeConfigReceiptIdentityProjection {
  static let empty = NativeRuntimeConfigReceiptIdentityProjection(
    environment: "",
    buildProfile: "",
    target: "",
    launchProvenance: "",
    runtimeConfigSupplyMode: "",
    packageDigest: "",
    trustEnvelopeDigest: "",
    effectiveLaunchManifestDigest: ""
  )

  let environment: String
  let buildProfile: String
  let target: String
  let launchProvenance: String
  let runtimeConfigSupplyMode: String
  let packageDigest: String
  let trustEnvelopeDigest: String
  let effectiveLaunchManifestDigest: String

  var isComplete: Bool {
    !environment.isEmpty
      && !buildProfile.isEmpty
      && !target.isEmpty
      && !launchProvenance.isEmpty
      && !runtimeConfigSupplyMode.isEmpty
      && !packageDigest.isEmpty
      && !trustEnvelopeDigest.isEmpty
      && !effectiveLaunchManifestDigest.isEmpty
  }
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
  private static let requestFields = Set(
    AppLaunchContract.runtimeConfigActivationRequestRequiredFields
  )
  private static let effectiveManifestFields = Set(
    AppLaunchContract.appEffectiveLaunchManifestRequiredFields
  )
  private static let transportFields = Set(
    AppLaunchContract.appEffectiveLaunchManifestTransportRequiredFields
  )
  private static let receiptFields = Set(
    AppLaunchContract.runtimeConfigActivationReceiptRequiredFields
  )
  private static let activatedReceiptStatus =
    AppLaunchContract.runtimeConfigActivationReceiptStatuses[0]
  private static let failedReceiptStatus =
    AppLaunchContract.runtimeConfigActivationReceiptStatuses[1]

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
    var receiptIdentity = NativeRuntimeConfigReceiptIdentityProjection.empty
    var requestDigest = canonicalDigest(expectedRequestDigest) ?? String(
      repeating: "0",
      count: 64
    ).withSHA256Prefix
    var previousActiveDigest = ""
    var previousActiveDigestKnown = false
    do {
      guard coldStartAllowed else {
        throw NativeRuntimeConfigReadError.activationRequiresColdStart
      }
      guard let normalizedRequestDigest = canonicalDigest(expectedRequestDigest) else {
        throw NativeRuntimeConfigReadError.activationRequestDigestInvalid
      }
      previousActiveDigest = try currentActiveDigest()
      previousActiveDigestKnown = true
      let requestURL = try runtimeConfigFileURL(
        name: nativeRuntimeActivationRequestFileName,
        createDirectory: false,
        requireExisting: true
      )
      let requestData = try readActivationData(requestURL)
      let decoded = try requestData.activationJSONObject()
      requestDigest = nativeSHA256Identity(try canonicalJSONData(decoded))
      receiptIdentity = validatedReceiptIdentityProjection(decoded)
      guard requestDigest == normalizedRequestDigest else {
        throw NativeRuntimeConfigReadError.activationRequestDigestMismatch
      }
      try validateRequest(decoded)
      guard receiptIdentity.isComplete else {
        throw NativeRuntimeConfigReadError.activationIdentityMismatch
      }
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
          identity: receiptIdentity,
          requestDigest: requestDigest,
          status: activatedReceiptStatus,
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
      let normalizedError = (error as? NativeRuntimeConfigReadError)
        ?? nativeRuntimeConfigInternalFailure(
          context: "consume_activation_request",
          error: error
        )
      var errorCode = normalizedError.flutterCode
      var issues = [errorCode]
      // 读取失败时状态未知：保持最后已知 CAS 值并追加 rollback_failed，不得宣称空 active，
      // 也不得覆盖原始失败码；只有确认读取成功且与 CAS 前不一致才升级为 rollback_failed。
      var activeDigest = previousActiveDigest
      var activeDigestUnknown = false
      do {
        activeDigest = try currentActiveDigest()
        if !previousActiveDigestKnown {
          previousActiveDigest = activeDigest
          previousActiveDigestKnown = true
        }
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
      var failedReceiptWritten = false
      do {
        let receipt = buildReceipt(
          identity: receiptIdentity,
          requestDigest: requestDigest,
          status: failedReceiptStatus,
          previousActiveDigest: previousActiveDigest,
          activePackageDigest: activeDigest,
          errorCode: errorCode,
          validationIssues: issues
        )
        try writeReceipt(receipt, name: nativeRuntimeActivationReceiptFileName)
        failedReceiptWritten = true
      } catch {
        if !issues.contains(NativeRuntimeConfigReadError.activationReceiptWriteFailed.flutterCode) {
          issues.append(NativeRuntimeConfigReadError.activationReceiptWriteFailed.flutterCode)
        }
      }
      if failedReceiptWritten,
         let requestURL = try? runtimeConfigFileURL(
           name: nativeRuntimeActivationRequestFileName,
           createDirectory: false,
           requireExisting: false
         )
      {
        try? FileManager.default.removeItem(at: requestURL)
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
      let code = ((error as? NativeRuntimeConfigReadError)
        ?? nativeRuntimeConfigInternalFailure(
          context: "read_recovery_runtime_context",
          error: error
        )).flutterCode
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
          receipt["schema"] as? String
            == AppLaunchContract.schemaValues["runtime_config_activation_receipt"],
          receipt["status"] as? String == activatedReceiptStatus,
          receipt["errorCode"] as? String == "",
          let issues = receipt["validationIssues"] as? [Any],
          issues.isEmpty,
          let launchProvenance = nonEmptyString(receipt["launchProvenance"]),
          AppLaunchContract.launchProvenances.contains(launchProvenance),
          let supplyMode = nonEmptyString(receipt["runtimeConfigSupplyMode"]),
          AppLaunchContract.runtimeConfigSupplyModes.contains(supplyMode),
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
      effectiveLaunchManifestDigest: manifestDigest,
      launchProvenance: launchProvenance,
      runtimeConfigSupplyMode: supplyMode
    )
  }

  static func validateRequest(_ request: [String: Any]) throws {
    guard Set(request.keys) == requestFields,
          request["schema"] as? String
            == AppLaunchContract.schemaValues["runtime_config_activation_request"],
          let environment = nonEmptyString(request["environment"]),
          let buildProfile = nonEmptyString(request["buildProfile"]),
          let target = nonEmptyString(request["target"]),
          AppLaunchContract.targetEnvironment[target] == environment,
          AppLaunchContract.buildProfileEnvironments[buildProfile]?.contains(environment) == true,
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
          manifest["schema"] as? String
            == AppLaunchContract.schemaValues["app_effective_launch_manifest"],
          let manifestEnvironment = nonEmptyString(manifest["environment"]),
          AppLaunchContract.environments.contains(manifestEnvironment),
          let manifestBuildProfile = nonEmptyString(manifest["buildProfile"]),
          let manifestTarget = nonEmptyString(manifest["target"]),
          AppLaunchContract.targetEnvironment[manifestTarget] == manifestEnvironment,
          manifest["entrypoint"] as? String
            == AppLaunchContract.appEffectiveLaunchManifestEntrypoint,
          let launchProvenance = nonEmptyString(manifest["launchProvenance"]),
          AppLaunchContract.launchProvenances.contains(launchProvenance),
          let supplyMode = nonEmptyString(manifest["runtimeConfigSupplyMode"]),
          AppLaunchContract.runtimeConfigSupplyModes.contains(supplyMode),
          let launchPolicy = nonEmptyString(manifest["launchPolicy"]),
          AppLaunchContract.buildProfileEnvironments[manifestBuildProfile]?
            .contains(manifestEnvironment) == true,
          AppLaunchContract.buildProfileLaunchPolicies[manifestBuildProfile] == launchPolicy,
          canonicalDigest(manifest["runtimeConfigPackageDigest"] as? String) != nil,
          canonicalDigest(manifest["runtimeConfigTrustEnvelopeDigest"] as? String) != nil,
          let requiresLocalTransport = strictBoolean(manifest["requiresLocalTransport"]),
          requiresLocalTransport == isLocalTransportTarget(manifestTarget),
          let transport = manifest["transport"] as? [String: Any],
          Set(transport.keys) == transportFields,
          let transportRequired = strictBoolean(transport["required"]),
          let reverseExpectedPorts = transport["reverseExpectedPorts"] as? String,
          let reverseActualPorts = transport["reverseActualPorts"] as? String,
          let reverseReceiptDigest = transport["reverseReceiptDigest"] as? String,
          let consumerLeaseID = transport["consumerLeaseId"] as? String
    else {
      throw NativeRuntimeConfigReadError.effectiveManifestMalformed
    }
    if transportRequired {
      guard isLocalTransportTarget(manifestTarget),
            canonicalDigest(reverseReceiptDigest) != nil,
            canonicalDigest(consumerLeaseID) != nil,
            let expectedPorts = canonicalPorts(reverseExpectedPorts),
            let actualPorts = canonicalPorts(reverseActualPorts),
            expectedPorts == actualPorts
      else {
        throw NativeRuntimeConfigReadError.effectiveManifestMalformed
      }
    } else {
      guard reverseExpectedPorts.isEmpty,
            reverseActualPorts.isEmpty,
            reverseReceiptDigest.isEmpty,
            consumerLeaseID.isEmpty
      else {
        throw NativeRuntimeConfigReadError.effectiveManifestMalformed
      }
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

  private static func validatedReceiptIdentityProjection(
    _ request: [String: Any]
  ) -> NativeRuntimeConfigReceiptIdentityProjection {
    guard request["schema"] as? String
            == AppLaunchContract.schemaValues["runtime_config_activation_request"],
          let environment = request["environment"] as? String,
          AppLaunchContract.environments.contains(environment),
          let buildProfile = request["buildProfile"] as? String,
          AppLaunchContract.buildProfileEnvironments[buildProfile]?
            .contains(environment) == true,
          let target = request["target"] as? String,
          AppLaunchContract.targetEnvironment[target] == environment,
          let packageDigest = canonicalDigest(request["packageDigest"] as? String),
          let trustEnvelopeDigest = canonicalDigest(
            request["trustEnvelopeDigest"] as? String
          ),
          let effectiveLaunchManifestDigest = canonicalDigest(
            request["effectiveLaunchManifestDigest"] as? String
          ),
          let package = request["package"] as? [String: Any],
          package["environment"] as? String == environment,
          package["buildProfile"] as? String == buildProfile,
          package["target"] as? String == target,
          let launchPolicy = package["launchPolicy"] as? String,
          AppLaunchContract.buildProfileLaunchPolicies[buildProfile] == launchPolicy,
          let calculatedPackageDigest = try? canonicalJSONData(package),
          nativeSHA256Identity(calculatedPackageDigest) == packageDigest,
          let manifest = request["effectiveLaunchManifest"] as? [String: Any],
          manifest["schema"] as? String
            == AppLaunchContract.schemaValues["app_effective_launch_manifest"],
          manifest["environment"] as? String == environment,
          manifest["buildProfile"] as? String == buildProfile,
          manifest["target"] as? String == target,
          manifest["launchPolicy"] as? String == launchPolicy,
          manifest["runtimeConfigPackageDigest"] as? String == packageDigest,
          manifest["runtimeConfigTrustEnvelopeDigest"] as? String
            == trustEnvelopeDigest,
          let launchProvenance = manifest["launchProvenance"] as? String,
          AppLaunchContract.launchProvenances.contains(launchProvenance),
          let runtimeConfigSupplyMode = manifest["runtimeConfigSupplyMode"] as? String,
          AppLaunchContract.runtimeConfigSupplyModes.contains(runtimeConfigSupplyMode),
          let calculatedManifest = try? canonicalJSONData(manifest),
          nativeSHA256Identity(calculatedManifest) == effectiveLaunchManifestDigest
    else {
      return .empty
    }
    return NativeRuntimeConfigReceiptIdentityProjection(
      environment: environment,
      buildProfile: buildProfile,
      target: target,
      launchProvenance: launchProvenance,
      runtimeConfigSupplyMode: runtimeConfigSupplyMode,
      packageDigest: packageDigest,
      trustEnvelopeDigest: trustEnvelopeDigest,
      effectiveLaunchManifestDigest: effectiveLaunchManifestDigest
    )
  }

  private static func strictBoolean(_ value: Any?) -> Bool? {
    guard let number = value as? NSNumber,
          CFGetTypeID(number) == CFBooleanGetTypeID()
    else {
      return nil
    }
    return number.boolValue
  }

  private static func isLocalTransportTarget(_ target: String) -> Bool {
    AppLaunchContract.localTransportTargets.contains(target)
  }

  private static func canonicalPorts(_ raw: String) -> Set<Int>? {
    var ports = Set<Int>()
    for component in raw.split(separator: ",", omittingEmptySubsequences: false) {
      let normalized = component.trimmingCharacters(in: .whitespacesAndNewlines)
      if normalized.isEmpty {
        continue
      }
      guard normalized.unicodeScalars.allSatisfy({ scalar in
        scalar.value >= 48 && scalar.value <= 57
      }),
        let port = Int(normalized),
        (1...65_535).contains(port)
      else {
        return nil
      }
      ports.insert(port)
    }
    return ports.isEmpty ? nil : ports
  }

  private static func buildReceipt(
    identity: NativeRuntimeConfigReceiptIdentityProjection,
    requestDigest: String,
    status: String,
    previousActiveDigest: String,
    activePackageDigest: String,
    errorCode: String,
    validationIssues: [String]
  ) -> [String: Any] {
    return [
      "schema": AppLaunchContract.schemaValues[
        "runtime_config_activation_receipt"
      ] ?? "",
      "status": status,
      "requestDigest": requestDigest,
      "environment": identity.environment,
      "buildProfile": identity.buildProfile,
      "target": identity.target,
      "launchProvenance": identity.launchProvenance,
      "runtimeConfigSupplyMode": identity.runtimeConfigSupplyMode,
      "packageDigest": identity.packageDigest,
      "trustEnvelopeDigest": identity.trustEnvelopeDigest,
      "effectiveLaunchManifestDigest": identity.effectiveLaunchManifestDigest,
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
    readFailedError: NativeRuntimeConfigReadError = .activationRequestReadFailed
  ) throws -> Data {
    let values: URLResourceValues
    do {
      values = try url.resourceValues(forKeys: [
        .isRegularFileKey,
        .isSymbolicLinkKey,
        .fileSizeKey,
      ])
    } catch {
      throw readFailedError
    }
    guard
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
    // 激活流程的 CAS 前值读取：豁免时间窗，其余校验保留。
    switch NativeRuntimeConfigStore.readActivePackageIdentity() {
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
            NativeRuntimeConfigReadError.activationReceiptMissing,
            NativeRuntimeConfigReadError.freshnessInvalid {
      // 过期旧包一定不是当前请求的目标包：交给完整 activate 流程替换，不得死锁。
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
    return normalized.isEmpty || normalized != value ? nil : value
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

}

private extension String {
  var withSHA256Prefix: String { "sha256:" + self }
}

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
