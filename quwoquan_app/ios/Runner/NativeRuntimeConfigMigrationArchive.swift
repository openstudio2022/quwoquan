// PreviousLayout predecessor migration archival. This file is compiled from the same shared
// source path by the production Runner and Patrol test host targets.

import Foundation

extension NativeRuntimeConfigStore {
  /// 仅供已完成 canonical request 校验的显式 activation 识别直接 predecessor。
  /// 历史文档仍按原始 bytes 验 canonical JSON、payload digest 与签名；绝不补字段重签。
  static func validatePreviousLayoutOfflinePredecessor(
    packageData: Data,
    trust: NativeRuntimeConfigTrustProjection,
    activeReceiptData: Data
  ) throws -> NativeRuntimeConfigActiveProjection {
    let package = try decodeDocument(packageData, malformedError: .packageMalformed)
    let activeReceipt = try decodeDocument(
      activeReceiptData,
      malformedError: .activationReceiptMalformed
    )
    let canonicalActiveReceiptData = try canonicalJSONData(activeReceipt)
    guard activeReceiptData == canonicalActiveReceiptData else {
      throw NativeRuntimeConfigReadError.activationReceiptMalformed
    }
    let projection = try validatePackage(
      package,
      packageData: packageData,
      trust: trust,
      expectedPackageDigest: nil,
      allowStaleIdentity: true,
      requiredFields: previousLayoutOfflinePredecessorFields
    )
    try validatePreviousLayoutActiveReceipt(activeReceipt, active: projection)
    return projection
  }

  /// 显式 activation 的一次性迁移探针。正常 reader/self-supply 不可达此入口。
  static func readExplicitActivationPredecessorIdentity()
    throws -> (digest: String, historical: Bool)
  {
    switch loadActivePackage(allowStaleIdentity: true) {
    case .present(let active):
      return (active.packageDigest, false)
    case .absent:
      return ("", false)
    case .failure(.schemaMismatch):
      let predecessor = try loadPreviousLayoutOfflinePredecessorArchive()
      return (predecessor.active.packageDigest, true)
    case .failure(let error):
      throw error
    }
  }

  struct PreviousLayoutOfflinePredecessorArchive {
    let active: NativeRuntimeConfigActiveProjection
    let packageData: Data
    let receiptData: Data
  }

  static func loadPreviousLayoutOfflinePredecessorArchive()
    throws -> PreviousLayoutOfflinePredecessorArchive
  {
    let trust = try loadTrustEnvelope()
    guard let packageURL = try runtimePackageURL(createDirectory: false) else {
      throw NativeRuntimeConfigReadError.packageMissing
    }
    let packageData = try readData(
      url: packageURL,
      pathError: .packagePathInvalid,
      readError: .packageReadFailed,
      emptyError: .packageEmpty,
      sizeError: .packageTooLarge
    )
    let receiptData = try NativeRuntimeConfigActivationCoordinator.readActiveReceiptData()
    let active = try validatePreviousLayoutOfflinePredecessor(
      packageData: packageData,
      trust: trust,
      activeReceiptData: receiptData
    )
    return PreviousLayoutOfflinePredecessorArchive(
      active: active,
      packageData: packageData,
      receiptData: receiptData
    )
  }

  static func archivePreviousLayoutMigrationHistory(
    packageData: Data,
    receiptData: Data,
    packageDigest: String,
    baseDirectory: URL,
    writeCreateOnce: ((Data, URL) throws -> Void)? = nil
  ) throws {
    guard let digest = digestIdentity(packageDigest),
          digest == nativeSHA256Identity(packageData)
    else {
      throw NativeRuntimeConfigReadError.packageDigestMismatch
    }
    let receiptDigest = nativeSHA256Identity(receiptData)
    let historyRoot = baseDirectory.appendingPathComponent(
      nativeRuntimeMigrationHistoryDirectory,
      isDirectory: true
    )
    let destination = historyRoot.appendingPathComponent(
      String(digest.dropFirst("sha256:".count)),
      isDirectory: true
    )
    try createDurableDirectory(historyRoot, parent: baseDirectory)
    let destinationExisted = try validatedDirectoryExists(destination)
    try createDurableDirectory(destination, parent: historyRoot)
    let audit: [String: Any] = [
      "schema": nativeRuntimePreviousLayoutAuditSchema,
      "packageDigest": digest,
      "receiptDigest": receiptDigest,
    ]
    let createOnce = writeCreateOnce ?? createOnceDurably
    do {
      try createOnce(
        packageData,
        destination.appendingPathComponent(nativeRuntimePreviousLayoutPackageArchiveFileName)
      )
      try createOnce(
        receiptData,
        destination.appendingPathComponent(nativeRuntimePreviousLayoutReceiptArchiveFileName)
      )
      try createOnce(
        try canonicalJSONData(audit),
        destination.appendingPathComponent(nativeRuntimePreviousLayoutAuditArchiveFileName)
      )
      try synchronizeDirectory(destination)
    } catch let error as NativeRuntimeConfigReadError {
      if !destinationExisted { try? FileManager.default.removeItem(at: destination) }
      throw error
    } catch {
      if !destinationExisted { try? FileManager.default.removeItem(at: destination) }
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
  }

  private static func validatedDirectoryExists(_ directory: URL) throws -> Bool {
    guard FileManager.default.fileExists(atPath: directory.path) else { return false }
    do {
      let values = try directory.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
      guard values.isDirectory == true, values.isSymbolicLink != true else {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
      return true
    } catch let error as NativeRuntimeConfigReadError {
      throw error
    } catch {
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
  }

  private static func createDurableDirectory(_ directory: URL, parent: URL) throws {
    let fileManager = FileManager.default
    if try validatedDirectoryExists(directory) { return }
    do {
      try fileManager.createDirectory(
        at: directory,
        withIntermediateDirectories: false,
        attributes: [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication]
      )
      try synchronizeDirectory(parent)
    } catch {
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
  }

  private static func createOnceDurably(_ data: Data, destination: URL) throws {
    let descriptor = open(destination.path, O_WRONLY | O_CREAT | O_EXCL, S_IRUSR | S_IWUSR)
    if descriptor < 0 {
      guard errno == EEXIST else {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
      let existing = try readData(
        url: destination,
        pathError: .activationWriteFailed,
        readError: .activationWriteFailed,
        emptyError: .activationWriteFailed,
        sizeError: .activationWriteFailed
      )
      guard existing == data else {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
      return
    }
    var succeeded = false
    defer {
      _ = close(descriptor)
      if !succeeded { try? FileManager.default.removeItem(at: destination) }
    }
    do {
      try FileManager.default.setAttributes(
        [.protectionKey: FileProtectionType.completeUntilFirstUserAuthentication],
        ofItemAtPath: destination.path
      )
      try data.withUnsafeBytes { rawBuffer in
        guard let base = rawBuffer.baseAddress else { return }
        var offset = 0
        while offset < rawBuffer.count {
          let count = write(descriptor, base.advanced(by: offset), rawBuffer.count - offset)
          guard count > 0 else { throw NativeRuntimeConfigReadError.activationWriteFailed }
          offset += count
        }
      }
      guard fsync(descriptor) == 0 else {
        throw NativeRuntimeConfigReadError.activationWriteFailed
      }
      succeeded = true
    } catch let error as NativeRuntimeConfigReadError {
      throw error
    } catch {
      throw NativeRuntimeConfigReadError.activationWriteFailed
    }
  }

  private static func validatePreviousLayoutActiveReceipt(
    _ receipt: [String: Any],
    active: NativeRuntimeConfigActiveProjection
  ) throws {
    let fields = Set(AppLaunchContract.runtimeConfigActivationReceiptRequiredFields)
    guard Set(receipt.keys) == fields,
          receipt["schema"] as? String
            == AppLaunchContract.schemaValues["runtime_config_activation_receipt"],
          receipt["status"] as? String
            == AppLaunchContract.runtimeConfigActivationReceiptStatuses[0],
          receipt["errorCode"] as? String == "",
          let issues = receipt["validationIssues"] as? [Any], issues.isEmpty,
          let provenance = receipt["launchProvenance"] as? String,
          AppLaunchContract.launchProvenances.contains(provenance),
          let supplyMode = receipt["runtimeConfigSupplyMode"] as? String,
          AppLaunchContract.runtimeConfigSupplyModes.contains(supplyMode),
          receipt["environment"] as? String == active.package["environment"] as? String,
          receipt["buildProfile"] as? String == active.package["buildProfile"] as? String,
          receipt["target"] as? String == active.package["target"] as? String,
          receipt["packageDigest"] as? String == active.packageDigest,
          receipt["activePackageDigest"] as? String == active.packageDigest,
          receipt["trustEnvelopeDigest"] as? String == active.trustEnvelopeDigest,
          digestIdentity(receipt["requestDigest"]) != nil,
          digestIdentity(receipt["effectiveLaunchManifestDigest"]) != nil,
          let previousDigest = receipt["previousActiveDigest"] as? String,
          previousDigest.isEmpty || digestIdentity(previousDigest) != nil
    else {
      throw NativeRuntimeConfigReadError.activationReceiptMismatch
    }
  }
}
