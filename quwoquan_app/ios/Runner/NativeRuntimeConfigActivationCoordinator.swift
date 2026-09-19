// Runtime config activation, receipt publication, and recovery coordination.

import CoreFoundation
import Foundation

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
      if let activeReceipt = try alreadyActivatedReceipt(
        request: decoded,
        requestDigest: requestDigest
      ) {
        try publishAlreadyActivatedReceipt(activeReceipt)
        try? FileManager.default.removeItem(at: requestURL)
        return NativeRuntimeConfigActivationConsumeResult(
          requested: true,
          activated: true,
          errorCode: "",
          validationIssues: []
        )
      }
      let predecessor = try NativeRuntimeConfigStore
        .readExplicitActivationPredecessorIdentity()
      previousActiveDigest = predecessor.digest
      previousActiveDigestKnown = true
      guard let requestedExpectedActiveDigest = decoded["expectedActiveDigest"] as? String,
            requestedExpectedActiveDigest == predecessor.digest
      else {
        throw NativeRuntimeConfigReadError.activeDigestConflict
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
        expectedActiveDigest: expectedActiveDigest,
        allowPreviousLayoutOfflinePredecessor: predecessor.historical
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
      return recordActivationFailure(
        error,
        context: "consume_activation_request",
        receiptIdentity: receiptIdentity,
        requestDigest: requestDigest,
        previousActiveDigest: previousActiveDigest,
        previousActiveDigestKnown: previousActiveDigestKnown,
        cleanupPendingRequestFile: true
      )
    }
  }

  /// Debug-nonprod 构建期自供给：冷启动无外部 activation 参数时消费制品内嵌的激活请求。
  ///
  /// 与外部请求走同一 validate → CAS activate → receipt 路径，区别只有两点：请求位于
  /// 制品而非私有容器，`expectedActiveDigest` 由这里以当前 active digest 现场补齐。
  /// 决策矩阵：制品无请求 → 未请求；合法在线 active → 保持不变；
  /// 缺席或已有合法 Alpha 离线且请求变化 → 激活；过期在线/损坏 → typed 失败，不回落。
  /// 失败只记账并返回 typed 码，调用方继续既有 trust/config 阻断，不得静默回退。
  static func consumeBundledSelfSupplyRequest() -> NativeRuntimeConfigActivationConsumeResult {
    let notRequested = NativeRuntimeConfigActivationConsumeResult(
      requested: false,
      activated: false,
      errorCode: "",
      validationIssues: []
    )
    guard let requestURL = Bundle.main.url(
      forResource: nativeRuntimeSelfSupplyRequestFileName,
      withExtension: nil,
      subdirectory: nativeRuntimeConfigDirectory
    ) else {
      return notRequested
    }
    var receiptIdentity = NativeRuntimeConfigReceiptIdentityProjection.empty
    var requestDigest = String(repeating: "0", count: 64).withSHA256Prefix
    var previousActiveDigest = ""
    var previousActiveDigestKnown = false
    do {
      let requestData = try readActivationData(requestURL)
      let decoded = try requestData.activationJSONObject()
      requestDigest = nativeSHA256Identity(try canonicalJSONData(decoded))
      receiptIdentity = validatedReceiptIdentityProjection(decoded)
      try validateRequest(decoded)
      guard receiptIdentity.isComplete,
            receiptIdentity.runtimeConfigSupplyMode == nativeRuntimeSelfSupplyMode,
            (decoded["effectiveLaunchManifest"] as? [String: Any])?["contentSource"] as? String == "bundled_snapshot",
            decoded["expectedActiveDigest"] as? String == ""
      else {
        throw NativeRuntimeConfigReadError.activationIdentityMismatch
      }
      switch NativeRuntimeConfigStore.readActivePackage() {
      case .present(let active):
        _ = try readVerifiedIdentity()
        let activeReceipt = try readActiveReceiptDocument()
        guard active.package["schema"] as? String == AppLaunchContract.schemaValues["offline_bootstrap_document"] else {
          NSLog("QWQStartup ios_runtime_config_self_supply_skipped reason=external_active")
          return notRequested
        }
        if activeReceipt["requestDigest"] as? String == requestDigest,
           active.packageDigest == receiptIdentity.packageDigest {
          return NativeRuntimeConfigActivationConsumeResult(
            requested: true,
            activated: true,
            errorCode: "",
            validationIssues: []
          )
        }
        previousActiveDigest = active.packageDigest
      case .absent:
        previousActiveDigest = ""
      case .failure(let error):
        // 只有显式 canonical activation 可以替换在线过期包；默认供给不降级权限。
        throw error
      }
      previousActiveDigestKnown = true
      guard let package = decoded["package"] as? [String: Any],
            let packageDigest = decoded["packageDigest"] as? String,
            let trustDigest = decoded["trustEnvelopeDigest"] as? String
      else {
        throw NativeRuntimeConfigReadError.activationRequestMalformed
      }
      _ = try NativeRuntimeConfigStore.activate(
        package: package,
        expectedPackageDigest: packageDigest,
        expectedTrustEnvelopeDigest: trustDigest,
        expectedActiveDigest: previousActiveDigest
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
      return NativeRuntimeConfigActivationConsumeResult(
        requested: true,
        activated: true,
        errorCode: "",
        validationIssues: []
      )
    } catch {
      return recordActivationFailure(
        error,
        context: "consume_self_supply_request",
        receiptIdentity: receiptIdentity,
        requestDigest: requestDigest,
        previousActiveDigest: previousActiveDigest,
        previousActiveDigestKnown: previousActiveDigestKnown,
        cleanupPendingRequestFile: false
      )
    }
  }

  private static func recordActivationFailure(
    _ error: Error,
    context: String,
    receiptIdentity: NativeRuntimeConfigReceiptIdentityProjection,
    requestDigest: String,
    previousActiveDigest initialPreviousActiveDigest: String,
    previousActiveDigestKnown initialPreviousActiveDigestKnown: Bool,
    cleanupPendingRequestFile: Bool
  ) -> NativeRuntimeConfigActivationConsumeResult {
    var previousActiveDigest = initialPreviousActiveDigest
    var previousActiveDigestKnown = initialPreviousActiveDigestKnown
    let normalizedError = (error as? NativeRuntimeConfigReadError)
      ?? nativeRuntimeConfigInternalFailure(
        context: context,
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
    if cleanupPendingRequestFile,
       failedReceiptWritten,
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

  // Active receipt 的缺席、读取失败与解码失败必须使用 receipt 语义错误码，
  // 不得复用 activation request 错误语义（metadata receipt 契约约束）。
  static func readActiveReceiptData() throws -> Data {
    let receiptURL = try runtimeConfigFileURL(
      name: nativeRuntimeActiveReceiptFileName,
      createDirectory: false,
      requireExisting: true,
      missingError: .activationReceiptMissing
    )
    return try readActivationData(
      receiptURL,
      malformedError: .activationReceiptMalformed,
      readFailedError: .activationReceiptReadFailed
    )
  }

  static func readActiveReceiptDocument() throws -> [String: Any] {
    let data = try readActiveReceiptData()
    let receipt = try data.activationJSONObject(malformedError: .activationReceiptMalformed)
    let canonicalReceiptData = try canonicalJSONData(receipt)
    guard data == canonicalReceiptData else {
      throw NativeRuntimeConfigReadError.activationReceiptMalformed
    }
    return receipt
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
      if AppLaunchContract.runtimeDocumentContentSources[active.package["schema"] as? String ?? ""] != "remote" {
        return .present([
          "runtimeEnvironment": active.package["environment"] as? String ?? "",
          "runtimeConfigDigest": identity.packageDigest,
          "effectiveLaunchManifestDigest": identity.effectiveLaunchManifestDigest,
          "contentSource": "bundled_snapshot",
        ])
      }
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
            == AppLaunchContract.appEffectiveLaunchManifestEntrypoint[
              AppLaunchContract.contentSourcePolicy[manifestEnvironment] ?? ""
            ],
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
          let contentSource = nonEmptyString(manifest["contentSource"]),
          contentSource == AppLaunchContract.contentSourcePolicy[manifestEnvironment],
          let requiresLocalTransport = strictBoolean(manifest["requiresLocalTransport"]),
          requiresLocalTransport == (contentSource == "remote" && isLocalTransportTarget(manifestTarget)),
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
      guard contentSource == "remote", isLocalTransportTarget(manifestTarget),
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
    guard AppLaunchContract.runtimeDocumentContentSources[package["schema"] as? String ?? ""] == contentSource,
          package["environment"] as? String == environment,
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

  private static func alreadyActivatedReceipt(
    request: [String: Any],
    requestDigest: String
  ) throws -> [String: Any]? {
    guard let expectedPackageDigest = request["packageDigest"] as? String,
          let expectedTrustDigest = request["trustEnvelopeDigest"] as? String,
          let expectedManifestDigest = request["effectiveLaunchManifestDigest"] as? String
    else {
      return nil
    }
    let identity: NativeRuntimeConfigActivationIdentity
    do {
      identity = try readVerifiedIdentity()
    } catch NativeRuntimeConfigReadError.packageMissing,
            NativeRuntimeConfigReadError.activationReceiptMissing,
            NativeRuntimeConfigReadError.freshnessInvalid,
            NativeRuntimeConfigReadError.contentSourceMismatch,
            NativeRuntimeConfigReadError.schemaMismatch {
      // 显式请求的 CAS 前值已验过签名/结构，旧包不作为候选；完整 activate 再验证新文档。
      return nil
    }
    let receipt = try readActiveReceiptDocument()
    guard receipt["requestDigest"] as? String == requestDigest,
          identity.packageDigest == expectedPackageDigest,
          identity.trustEnvelopeDigest == expectedTrustDigest,
          identity.effectiveLaunchManifestDigest == expectedManifestDigest
    else {
      return nil
    }
    return receipt
  }

  private static func publishAlreadyActivatedReceipt(
    _ activeReceipt: [String: Any]
  ) throws {
    try publishAlreadyActivatedReceipt(activeReceipt) { receipt, name in
      try writeReceipt(receipt, name: name)
    }
  }

  static func publishAlreadyActivatedReceipt(
    _ activeReceipt: [String: Any],
    write: ([String: Any], String) throws -> Void
  ) throws {
    do {
      // active receipt 已由 readVerifiedIdentity/readActiveReceiptDocument 完整校验；
      // 这里只把同一 canonical 文档发布为本次 launch receipt，不重写 active 身份。
      try write(activeReceipt, nativeRuntimeActivationReceiptFileName)
    } catch {
      throw NativeRuntimeConfigReadError.activationReceiptWriteFailed
    }
  }

  private static func canonicalJSONData(_ document: [String: Any]) throws -> Data {
    guard JSONSerialization.isValidJSONObject(document) else {
      throw NativeRuntimeConfigReadError.activationRequestMalformed
    }
    do {
      return try NativeRuntimeCanonicalJSON.data(document)
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
