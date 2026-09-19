// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import CryptoKit
import Flutter
import EventKit
import UIKit
import XCTest
@testable import Runner

class RunnerTests: XCTestCase {

  func testStartupSafeTerminalSurfacePreservesDartRecoveryIdentity() {
    XCTAssertEqual(
      StartupSafeTerminalSurface.parse(event: startupTerminalEvent("router_shell")),
      .routerShell
    )
    XCTAssertEqual(
      StartupSafeTerminalSurface.parse(event: startupTerminalEvent("safe_recovery")),
      .safeRecovery
    )
    XCTAssertEqual(
      StartupSafeTerminalSurface.parse(event: startupTerminalEvent("flutter_recovery")),
      .flutterRecovery
    )
    XCTAssertTrue(StartupSafeTerminalSurface.routerShell.isCanonical)
    XCTAssertFalse(StartupSafeTerminalSurface.safeRecovery.isCanonical)
    XCTAssertFalse(StartupSafeTerminalSurface.flutterRecovery.isCanonical)
  }

  func testStartupSafeTerminalSurfaceRejectsMissingAndUnknownValues() {
    XCTAssertEqual(
      StartupSafeTerminalSurface.parse(
        event: "{\"eventName\":\"startup_safe_terminal\"}"
      ),
      .missing
    )
    XCTAssertEqual(
      StartupSafeTerminalSurface.parse(event: startupTerminalEvent("future_surface")),
      .unknown
    )
    XCTAssertFalse(StartupSafeTerminalSurface.missing.isCanonical)
    XCTAssertFalse(StartupSafeTerminalSurface.unknown.isCanonical)
  }

  func testIOSNativeRecoveryAcceptsCanonicalNullableUpdateWire() throws {
    let available = try XCTUnwrap(
      NativeRecoveryVersionResponse.parse(
        payload: recoveryVersionPayload(updateState: "available"),
        expectedPlatform: "ios",
        currentBuild: 18_100,
        isTrustedURL: trustedRecoveryURL
      )
    )
    XCTAssertEqual(available.platform, "ios")
    XCTAssertEqual(available.latestVersion, "1.8.2")
    XCTAssertEqual(available.latestBuild, 18_201)
    XCTAssertEqual(available.minimumSupportedVersion, "1.8.0")
    XCTAssertEqual(available.minimumSupportedBuild, 18_000)
    XCTAssertEqual(available.updateState, .available)
    XCTAssertNil(available.updateURL)
    XCTAssertEqual(
      available.recoveryURL,
      "https://download.quwoquan.example/download/ios"
    )
    XCTAssertTrue(available.hasNewerVersion)
    XCTAssertFalse(available.offersNativeUpdate)

    let required = try XCTUnwrap(
      NativeRecoveryVersionResponse.parse(
        payload: recoveryVersionPayload(updateState: "required"),
        expectedPlatform: "ios",
        currentBuild: 17_999,
        isTrustedURL: trustedRecoveryURL
      )
    )
    XCTAssertEqual(required.updateState, .required)
    XCTAssertTrue(required.hasNewerVersion)
    XCTAssertFalse(required.offersNativeUpdate)
  }

  func testIOSNativeRecoveryRejectsNonCanonicalOrUntrustedWire() {
    var extra = recoveryVersionPayload(updateState: "available")
    extra["unexpected"] = "field"
    XCTAssertNil(parseIOSRecovery(extra))

    var missing = recoveryVersionPayload(updateState: "available")
    missing.removeValue(forKey: "latestVersion")
    XCTAssertNil(parseIOSRecovery(missing))

    var wrongPlatform = recoveryVersionPayload(updateState: "available")
    wrongPlatform["platform"] = "android"
    XCTAssertNil(parseIOSRecovery(wrongPlatform))

    var nonNullableUpdate = recoveryVersionPayload(updateState: "available")
    nonNullableUpdate["updateUrl"] = "https://download.quwoquan.example/app-store"
    XCTAssertNil(parseIOSRecovery(nonNullableUpdate))

    var invalidMinimum = recoveryVersionPayload(updateState: "available")
    invalidMinimum["minimumSupportedBuild"] = "19000"
    XCTAssertNil(parseIOSRecovery(invalidMinimum))

    var inconsistentState = recoveryVersionPayload(updateState: "none")
    inconsistentState["minimumSupportedBuild"] = "18000"
    XCTAssertNil(parseIOSRecovery(inconsistentState))

    var untrustedRecovery = recoveryVersionPayload(updateState: "available")
    untrustedRecovery["recoveryUrl"] = "https://attacker.example/download/ios"
    XCTAssertNil(parseIOSRecovery(untrustedRecovery))
  }

  // spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008
  #if targetEnvironment(simulator) && QWQ_EXTERNAL_UAT_BROKER
  func testGwt008BrokerUsesAttemptRandomRestrictedUnixSocket() throws {
    let directory = FileManager.default.temporaryDirectory
      .appendingPathComponent(UUID().uuidString, isDirectory: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let driver = AlphaGwt008NativeEvidenceDriver()
    let path = try driver.startUATBroker(
      socketDirectory: directory,
      randomComponent: "01234567-89ab-cdef-0123456789ab"
    )
    var mode: UInt16 = 0
    XCTAssertEqual(lstat(path, nil), 0)
    let attributes = try FileManager.default.attributesOfItem(atPath: path)
    mode = (attributes[.posixPermissions] as? NSNumber)?.uint16Value ?? 0
    XCTAssertEqual(mode, 0o600)
    XCTAssertTrue(path.hasSuffix(".sock"))
    XCTAssertFalse(path.contains("verifier"))
    driver.revoke()
    XCTAssertFalse(FileManager.default.fileExists(atPath: path))
  }

  func testGwt008StartBrokerWithoutHostIdentityIsRejected() {
    let driver = AlphaGwt008NativeEvidenceDriver()
    XCTAssertThrowsError(try driver.startUATBroker()) {
      XCTAssertEqual($0 as? AlphaGwt008NativeEvidenceDriver.Failure, .typed("APP.UAT.relay_admission_mismatch"))
    }
  }

  func testGwt008NativeEvidenceCreateOnceAndExactFence() throws {
    let now: TimeInterval = 100
    let pid = ProcessInfo.processInfo.processIdentifier
    let driver = AlphaGwt008NativeEvidenceDriver(processId: pid, startedUptime: 1.5, now: { now })
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: directory) }
    var admission = gwt008Admission(pid: pid, nowMs: 100_000)
    let body = admission
    admission["admissionDigest"] = try gwt008Digest(body)
    _ = try driver.arm(admission: admission, verifierHex: String(repeating: "ab", count: 32),
                       launcherPid: getpid(), socketDirectory: directory,
                       randomComponent: "01234567-89ab-cdef-0123456789ab")
    let snapshot: [String: Any] = [
      "schema": "external-uat-sealed-snapshot", "caseId": "login-success",
      "launchAttemptId": "attempt-1", "generation": 1,
      "observationBinding": gwt008DigestValue("binding"),
      "observations": [["source": "auth", "status": "observed", "detail": "local-success"]],
    ]
    var injected = snapshot; injected["processId"] = pid
    XCTAssertThrowsError(try driver.sealObservation(injected))
    injected = snapshot; injected["sealedAtMonotonicMs"] = 100_001
    XCTAssertThrowsError(try driver.sealObservation(injected))
    let first = try driver.sealObservation(snapshot)
    var nativeSnapshot = snapshot
    nativeSnapshot["processId"] = pid
    nativeSnapshot["sealedAtMonotonicMs"] = Int64(100_000)
    XCTAssertEqual(first, try gwt008Digest(nativeSnapshot))
    XCTAssertEqual(try driver.sealObservation(snapshot), first)
    var conflict = snapshot; conflict["observations"] = []
    XCTAssertThrowsError(try driver.sealObservation(conflict))
  }

  func testGwt008ObservationAndQueryDeadlinesAreIndependent() throws {
    var now: TimeInterval = 100
    let pid = getpid()
    let driver = AlphaGwt008NativeEvidenceDriver(processId: pid, now: { now })
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { driver.revoke(); try? FileManager.default.removeItem(at: directory) }
    var admission = gwt008Admission(pid: pid, nowMs: 100_000)
    admission["caseId"] = "otp-expiry"
    admission["expiresAtMonotonicMs"] = Int64(460_000)
    admission["admissionDigest"] = try gwt008Digest(admission)
    _ = try driver.arm(admission: admission, verifierHex: String(repeating: "ab", count: 32),
                       launcherPid: getpid(), socketDirectory: directory)
    now = 400
    let snapshot: [String: Any] = ["schema": "external-uat-sealed-snapshot", "caseId": "otp-expiry",
      "launchAttemptId": "attempt-1", "generation": 1, "observationBinding": gwt008DigestValue("binding"),
      "observations": [["source": "monotonic-clock", "status": "observed", "detail": "elapsed-300s-challenge-expired"]]]
    let sealed = try driver.sealObservation(snapshot)
    now = 459
    XCTAssertEqual(try driver.sealObservation(snapshot), sealed)
    now = 461
    XCTAssertThrowsError(try driver.query([:], peerPid: pid, peerEuid: geteuid())) {
      XCTAssertEqual($0 as? AlphaGwt008NativeEvidenceDriver.Failure, .typed("APP.UAT.relay_expired"))
    }
  }

  func testGwt008RejectsStaleAdmissionAndSensitiveSnapshot() throws {
    let pid = ProcessInfo.processInfo.processIdentifier
    let driver = AlphaGwt008NativeEvidenceDriver(processId: pid, now: { 100 })
    var admission = gwt008Admission(pid: pid, nowMs: 100_000)
    admission["expiresAtMonotonicMs"] = 99_999
    admission["admissionDigest"] = try gwt008Digest(admission)
    XCTAssertThrowsError(try driver.arm(admission: admission,
      verifierHex: String(repeating: "ab", count: 32), launcherPid: getpid(),
      socketDirectory: FileManager.default.temporaryDirectory,
      randomComponent: "01234567-89ab-cdef-0123456789ab"))
  }

  func testGwt008NativeEvidenceBindsAttemptAndRedactsInput() throws {
    let driver = AlphaGwt008NativeEvidenceDriver(processId: 42, startedUptime: 1.5)
    let process = try driver.processObservation(attemptId: "attempt-1")
    XCTAssertEqual(process["processId"] as? Int32, 42)
    XCTAssertEqual(process["launchAttemptId"] as? String, "attempt-1")
    let observation = try driver.redactedInputObservation([
      "contractDigest": canonicalDigest("a"), "caseId": "login-success",
      "selector": "rehearsal-confirm-input", "sourceSelector": "alpha-rehearsal-confirm", "mode": "correct",
    ])
    XCTAssertEqual(observation["observed"] as? String, "input-redacted")
    XCTAssertFalse(String(describing: observation).contains("123456"))
  }

  private func gwt008Admission(pid: pid_t, nowMs: Int64) -> [String: Any] {
    let digest = gwt008DigestValue("value")
    return [
      "schema": "external-uat-managed-launch-admission", "contractDigest": digest,
      "candidateDigest": digest, "artifactDigest": digest, "packageIdentity": "com.leadwise.quwoquan.alpha.debug",
      "signingDigest": digest, "platform": "ios-simulator", "deviceId": "simulator-1",
      "sessionId": "session-1", "caseId": "login-success", "launchAttemptId": "attempt-1",
      "generation": 1, "observationBinding": gwt008DigestValue("binding"), "processId": pid,
      "lifecycleReceiptDigest": digest, "admittedAtMonotonicMs": nowMs,
      "expiresAtMonotonicMs": nowMs + 60_000,
    ]
  }

  private func gwt008Digest(_ value: [String: Any]) throws -> String {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
    return "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  private func gwt008DigestValue(_ value: String) -> String {
    "sha256:" + SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
  }
  #endif

  private func startupTerminalEvent(_ surface: String) -> String {
    "{\"eventName\":\"startup_safe_terminal\",\"surface\":\"\(surface)\"}"
  }

  private func recoveryVersionPayload(updateState: String) -> [String: Any] {
    [
      "platform": "ios",
      "latestVersion": "1.8.2",
      "latestBuild": "18201",
      "minimumSupportedVersion": "1.8.0",
      "minimumSupportedBuild": "18000",
      "updateState": updateState,
      "updateUrl": NSNull(),
      "recoveryUrl": "https://download.quwoquan.example/download/ios",
    ]
  }

  private func parseIOSRecovery(
    _ payload: [String: Any]
  ) -> NativeRecoveryVersionResponse? {
    NativeRecoveryVersionResponse.parse(
      payload: payload,
      expectedPlatform: "ios",
      currentBuild: 18_100,
      isTrustedURL: trustedRecoveryURL
    )
  }

  private func trustedRecoveryURL(_ url: URL?) -> Bool {
    url?.scheme == "https" && url?.host == "download.quwoquan.example"
  }

  func testRuntimeConfigReadFailuresPreserveCanonicalTypedErrors() throws {
    XCTAssertEqual(
      NativeRuntimeConfigReadError.trustMissing.flutterCode,
      "runtime_config_trust_missing"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.trustReadFailed.flutterCode,
      "runtime_config_trust_read_failed"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.trustEmpty.flutterCode,
      "runtime_config_trust_empty"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.trustTooLarge.flutterCode,
      "runtime_config_trust_too_large"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.trustMalformed.flutterCode,
      "runtime_config_trust_malformed"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.packageMissing.flutterCode,
      "runtime_config_package_missing"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.packageReadFailed.flutterCode,
      "runtime_config_package_read_failed"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.packageEmpty.flutterCode,
      "runtime_config_package_empty"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.packageTooLarge.flutterCode,
      "runtime_config_package_too_large"
    )
    XCTAssertEqual(
      NativeRuntimeConfigReadError.packageMalformed.flutterCode,
      "runtime_config_package_malformed"
    )

    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(
      "ios-runtime-config-read-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }

    let empty = directory.appendingPathComponent("empty.json")
    try Data().write(to: empty)
    assertRuntimeConfigError(.packageEmpty) {
      _ = try NativeRuntimeConfigStore.readData(
        url: empty,
        pathError: .packagePathInvalid,
        readError: .packageReadFailed,
        emptyError: .packageEmpty,
        sizeError: .packageTooLarge
      )
    }

    let oversized = directory.appendingPathComponent("oversized.json")
    try Data(repeating: 0x20, count: 1024 * 1024 + 1).write(to: oversized)
    assertRuntimeConfigError(.packageTooLarge) {
      _ = try NativeRuntimeConfigStore.readData(
        url: oversized,
        pathError: .packagePathInvalid,
        readError: .packageReadFailed,
        emptyError: .packageEmpty,
        sizeError: .packageTooLarge
      )
    }

    let readable = directory.appendingPathComponent("readable.json")
    try Data("{}".utf8).write(to: readable)
    assertRuntimeConfigError(.packageReadFailed) {
      _ = try NativeRuntimeConfigStore.readData(
        url: readable,
        pathError: .packagePathInvalid,
        readError: .packageReadFailed,
        emptyError: .packageEmpty,
        sizeError: .packageTooLarge,
        load: { _ in throw CocoaError(.fileReadUnknown) }
      )
    }
    assertRuntimeConfigError(.packageMalformed) {
      _ = try NativeRuntimeConfigStore.decodeDocument(
        Data("not-json".utf8),
        malformedError: .packageMalformed
      )
    }
  }

  func testRuntimeConfigKeyringRuntimeAndSourceIdentityUseDedicatedErrors() throws {
    let canonicalKey = Data(repeating: 0x01, count: 32).base64EncodedString()
    XCTAssertNoThrow(
      try NativeRuntimeConfigStore.normalizedKeyring(
        ["nonprod-key": canonicalKey],
        invalidError: .trustKeyringInvalid
      )
    )
    assertRuntimeConfigError(.trustKeyringInvalid) {
      _ = try NativeRuntimeConfigStore.normalizedKeyring(
        [:],
        invalidError: .trustKeyringInvalid
      )
    }
    assertRuntimeConfigError(.keyringMismatch) {
      _ = try NativeRuntimeConfigStore.normalizedKeyring(
        ["invalid key id": canonicalKey],
        invalidError: .keyringMismatch
      )
    }
    assertRuntimeConfigError(.trustKeyringInvalid) {
      _ = try NativeRuntimeConfigStore.normalizedKeyring(
        ["-leading-symbol": canonicalKey],
        invalidError: .trustKeyringInvalid
      )
    }

    XCTAssertNoThrow(
      try NativeRuntimeConfigStore.validateSourceIdentity([
        "sourceGitSha": String(repeating: "a", count: 40),
        "sourceTreeDigest": "sha1:" + String(repeating: "b", count: 40),
      ])
    )
    XCTAssertNoThrow(
      try NativeRuntimeConfigStore.validateSourceIdentity([
        "sourceGitSha": String(repeating: "a", count: 40),
        "sourceTreeDigest": "sha256:" + String(repeating: "b", count: 64),
      ])
    )
    for invalidTreeDigest in [
      "sha1:" + String(repeating: "b", count: 39),
      "sha1:" + String(repeating: "b", count: 41),
      "sha256:" + String(repeating: "b", count: 63),
      "sha256:" + String(repeating: "b", count: 65),
    ] {
      assertRuntimeConfigError(.sourceIdentityInvalid) {
        try NativeRuntimeConfigStore.validateSourceIdentity([
          "sourceGitSha": String(repeating: "a", count: 40),
          "sourceTreeDigest": invalidTreeDigest,
        ])
      }
    }

    let runtime = canonicalRuntimeValues(environment: "alpha")
    XCTAssertNoThrow(
      try NativeRuntimeConfigStore.validateRuntimeValues(runtime, environment: "alpha")
    )
    var wrongType = runtime
    wrongType["gatewayBaseUrl"] = 443
    assertRuntimeConfigError(.runtimeValuesInvalid) {
      _ = try NativeRuntimeConfigStore.validateRuntimeValues(wrongType, environment: "alpha")
    }
    var insecureEndpoint = runtime
    insecureEndpoint["gatewayBaseUrl"] = "http://api.quwoquan.example"
    assertRuntimeConfigError(.endpointInvalid) {
      _ = try NativeRuntimeConfigStore.validateRuntimeValues(
        insecureEndpoint,
        environment: "alpha"
      )
    }
  }

  func testEffectiveLaunchManifestAcceptsCanonicalTopology() throws {
    XCTAssertNoThrow(
      try NativeRuntimeConfigActivationCoordinator.validateRequest(
        try activationRequest(
          manifest: effectiveLaunchManifest(
            environment: "alpha",
            buildProfile: "nonprod",
            target: "alpha-local",
            launchPolicy: "test_live",
            requiresLocalTransport: true,
            transportRequired: true
          )
        )
      )
    )
    XCTAssertNoThrow(
      try NativeRuntimeConfigActivationCoordinator.validateRequest(
        try activationRequest(
          manifest: effectiveLaunchManifest(
            environment: "prod",
            buildProfile: "prod",
            target: "prod-hosted",
            launchPolicy: "prod_release",
            requiresLocalTransport: false,
            transportRequired: false
          ),
          environment: "prod",
          buildProfile: "prod",
          target: "prod-hosted",
          launchPolicy: "prod_release"
        )
      )
    )
  }

  func testEffectiveLaunchManifestRejectsInvalidTypesTopologyDigestAndLease() throws {
    let canonical = effectiveLaunchManifest(
      environment: "alpha",
      buildProfile: "nonprod",
      target: "alpha-local",
      launchPolicy: "test_live",
      requiresLocalTransport: true,
      transportRequired: true
    )
    var invalidManifests: [[String: Any]] = []

    var wrongTopologyType = canonical
    wrongTopologyType["requiresLocalTransport"] = "true"
    invalidManifests.append(wrongTopologyType)

    var wrongTransportType = canonical
    var transport = wrongTransportType["transport"] as! [String: Any]
    transport["required"] = "true"
    wrongTransportType["transport"] = transport
    invalidManifests.append(wrongTransportType)

    var wrongPortType = canonical
    transport = wrongPortType["transport"] as! [String: Any]
    transport["reverseActualPorts"] = 443
    wrongPortType["transport"] = transport
    invalidManifests.append(wrongPortType)

    var mismatchedPorts = canonical
    transport = mismatchedPorts["transport"] as! [String: Any]
    transport["reverseActualPorts"] = "444"
    mismatchedPorts["transport"] = transport
    invalidManifests.append(mismatchedPorts)

    var invalidReceiptDigest = canonical
    transport = invalidReceiptDigest["transport"] as! [String: Any]
    transport["reverseReceiptDigest"] = "sha256:short"
    invalidReceiptDigest["transport"] = transport
    invalidManifests.append(invalidReceiptDigest)

    var invalidLease = canonical
    transport = invalidLease["transport"] as! [String: Any]
    transport["consumerLeaseId"] = "lease-1"
    invalidLease["transport"] = transport
    invalidManifests.append(invalidLease)

    var unexpectedEvidence = canonical
    transport = unexpectedEvidence["transport"] as! [String: Any]
    transport["required"] = false
    unexpectedEvidence["transport"] = transport
    invalidManifests.append(unexpectedEvidence)

    var wrongLocalTopology = canonical
    wrongLocalTopology["requiresLocalTransport"] = false
    transport = wrongLocalTopology["transport"] as! [String: Any]
    transport["required"] = false
    transport["reverseExpectedPorts"] = ""
    transport["reverseActualPorts"] = ""
    transport["reverseReceiptDigest"] = ""
    transport["consumerLeaseId"] = ""
    wrongLocalTopology["transport"] = transport
    invalidManifests.append(wrongLocalTopology)

    var malformedPackageDigest = canonical
    malformedPackageDigest["runtimeConfigPackageDigest"] = "sha256:short"
    invalidManifests.append(malformedPackageDigest)

    var nonCanonicalProvenance = canonical
    nonCanonicalProvenance["launchProvenance"] = " canonical_launcher"
    invalidManifests.append(nonCanonicalProvenance)

    for manifest in invalidManifests {
      assertRuntimeConfigError(.effectiveManifestMalformed) {
        try NativeRuntimeConfigActivationCoordinator.validateRequest(
          try activationRequest(manifest: manifest)
        )
      }
    }

    var digestDrift = try activationRequest(manifest: canonical)
    digestDrift["effectiveLaunchManifestDigest"] = canonicalDigest("f")
    assertRuntimeConfigError(.effectiveManifestDigestMismatch) {
      try NativeRuntimeConfigActivationCoordinator.validateRequest(digestDrift)
    }

    var packageIdentityDrift = try activationRequest(manifest: canonical)
    var package = packageIdentityDrift["package"] as! [String: Any]
    package["environment"] = "beta"
    packageIdentityDrift["package"] = package
    assertRuntimeConfigError(.activationIdentityMismatch) {
      try NativeRuntimeConfigActivationCoordinator.validateRequest(packageIdentityDrift)
    }

    var nonCanonicalRequestIdentity = try activationRequest(manifest: canonical)
    nonCanonicalRequestIdentity["environment"] = "alpha "
    assertRuntimeConfigError(.activationRequestMalformed) {
      try NativeRuntimeConfigActivationCoordinator.validateRequest(nonCanonicalRequestIdentity)
    }
  }

  func testInvalidEffectiveManifestCannotReachActivatedState() throws {
    try withPreservedRuntimeConfigFiles { directory in
      let packageURL = directory.appendingPathComponent(
        "runtime-config-package.json",
        isDirectory: false
      )
      let requestURL = directory.appendingPathComponent(
        "runtime-config-activation-request.json",
        isDirectory: false
      )
      try? FileManager.default.removeItem(at: packageURL)
      var manifest = effectiveLaunchManifest(
        environment: "alpha",
        buildProfile: "nonprod",
        target: "alpha-local",
        launchPolicy: "test_live",
        requiresLocalTransport: true,
        transportRequired: true
      )
      var transport = manifest["transport"] as! [String: Any]
      transport["consumerLeaseId"] = "not-a-digest"
      manifest["transport"] = transport
      let request = try activationRequest(manifest: manifest)
      let data = try JSONSerialization.data(
        withJSONObject: request,
        options: [.sortedKeys, .withoutEscapingSlashes]
      )
      try data.write(to: requestURL)
      let requestDigest = "sha256:" + SHA256.hash(data: data).map {
        String(format: "%02x", $0)
      }.joined()

      let result = NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
        arguments: [
          "--qwq-runtime-config-activation-request-digest",
          requestDigest,
        ],
        coldStartAllowed: true
      )

      XCTAssertTrue(result.requested)
      XCTAssertFalse(result.activated)
      XCTAssertEqual(
        result.errorCode,
        NativeRuntimeConfigReadError.effectiveManifestMalformed.flutterCode
      )
      XCTAssertFalse(FileManager.default.fileExists(atPath: packageURL.path))
    }
  }

  func testFailedActivationReceiptUsesEmptyIdentityForMissingAndUndecodableRequest() throws {
    try withPreservedRuntimeConfigFiles { directory in
      let packageURL = runtimeConfigFileURL(
        "runtime-config-package.json",
        in: directory
      )
      let requestURL = runtimeConfigFileURL(
        "runtime-config-activation-request.json",
        in: directory
      )
      let launchReceiptURL = runtimeConfigFileURL(
        "runtime-config-activation-receipt.json",
        in: directory
      )
      let activeReceiptURL = runtimeConfigFileURL(
        "runtime-config-active-receipt.json",
        in: directory
      )
      try? FileManager.default.removeItem(at: packageURL)
      try? FileManager.default.removeItem(at: requestURL)
      try? FileManager.default.removeItem(at: launchReceiptURL)
      let activeReceiptSentinel = Data("preserve-active-receipt".utf8)
      try activeReceiptSentinel.write(to: activeReceiptURL)

      let missingDigest = canonicalDigest("e")
      let missing = NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
        arguments: [
          "--qwq-runtime-config-activation-request-digest",
          missingDigest,
        ],
        coldStartAllowed: true
      )

      XCTAssertEqual(
        missing.errorCode,
        NativeRuntimeConfigReadError.activationRequestMissing.flutterCode
      )
      let missingReceipt = try readRuntimeConfigReceipt(launchReceiptURL)
      XCTAssertEqual(missingReceipt["status"] as? String, "failed")
      XCTAssertEqual(missingReceipt["requestDigest"] as? String, missingDigest)
      assertEmptyRuntimeConfigReceiptIdentity(missingReceipt)
      XCTAssertEqual(try Data(contentsOf: activeReceiptURL), activeReceiptSentinel)

      try Data("{".utf8).write(to: requestURL)
      let malformedDigest = canonicalDigest("f")
      let malformed = NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
        arguments: [
          "--qwq-runtime-config-activation-request-digest",
          malformedDigest,
        ],
        coldStartAllowed: true
      )

      XCTAssertEqual(
        malformed.errorCode,
        NativeRuntimeConfigReadError.activationRequestMalformed.flutterCode
      )
      let malformedReceipt = try readRuntimeConfigReceipt(launchReceiptURL)
      XCTAssertEqual(malformedReceipt["requestDigest"] as? String, malformedDigest)
      assertEmptyRuntimeConfigReceiptIdentity(malformedReceipt)
      XCTAssertEqual(try Data(contentsOf: activeReceiptURL), activeReceiptSentinel)
    }
  }

  func testFailedActivationReceiptDoesNotEchoInvalidDecodedIdentity() throws {
    try withPreservedRuntimeConfigFiles { directory in
      try? FileManager.default.removeItem(
        at: runtimeConfigFileURL("runtime-config-package.json", in: directory)
      )
      var request = try activationRequest(
        manifest: effectiveLaunchManifest(
          environment: "alpha",
          buildProfile: "nonprod",
          target: "alpha-local",
          launchPolicy: "test_live",
          requiresLocalTransport: true,
          transportRequired: false
        )
      )
      request["environment"] = "attacker-controlled"
      let requestDigest = try writeActivationRequest(request, in: directory)

      let result = NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
        arguments: [
          "--qwq-runtime-config-activation-request-digest",
          requestDigest,
        ],
        coldStartAllowed: true
      )

      XCTAssertEqual(
        result.errorCode,
        NativeRuntimeConfigReadError.activationRequestMalformed.flutterCode
      )
      let receipt = try readRuntimeConfigReceipt(
        runtimeConfigFileURL(
          "runtime-config-activation-receipt.json",
          in: directory
        )
      )
      assertEmptyRuntimeConfigReceiptIdentity(receipt)
    }
  }

  func testFailedActivationReceiptPreservesValidatedPostDecodeIdentity() throws {
    try withPreservedRuntimeConfigFiles { directory in
      try? FileManager.default.removeItem(
        at: runtimeConfigFileURL("runtime-config-package.json", in: directory)
      )
      var manifest = effectiveLaunchManifest(
        environment: "alpha",
        buildProfile: "nonprod",
        target: "alpha-local",
        launchPolicy: "test_live",
        requiresLocalTransport: true,
        transportRequired: false
      )
      var request = try activationRequest(manifest: manifest)
      let package = try XCTUnwrap(request["package"] as? [String: Any])
      let packageDigest = try canonicalJSONDigest(package)
      manifest["runtimeConfigPackageDigest"] = packageDigest
      request["packageDigest"] = packageDigest
      request["effectiveLaunchManifest"] = manifest
      request["effectiveLaunchManifestDigest"] = try canonicalJSONDigest(manifest)
      let requestDigest = try writeActivationRequest(request, in: directory)

      let result = NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
        arguments: [
          "--qwq-runtime-config-activation-request-digest",
          requestDigest,
        ],
        coldStartAllowed: true
      )

      XCTAssertEqual(
        result.errorCode,
        NativeRuntimeConfigReadError.trustDigestMismatch.flutterCode
      )
      let receipt = try readRuntimeConfigReceipt(
        runtimeConfigFileURL(
          "runtime-config-activation-receipt.json",
          in: directory
        )
      )
      XCTAssertEqual(receipt["environment"] as? String, request["environment"] as? String)
      XCTAssertEqual(receipt["buildProfile"] as? String, request["buildProfile"] as? String)
      XCTAssertEqual(receipt["target"] as? String, request["target"] as? String)
      XCTAssertEqual(receipt["packageDigest"] as? String, request["packageDigest"] as? String)
      XCTAssertEqual(
        receipt["trustEnvelopeDigest"] as? String,
        request["trustEnvelopeDigest"] as? String
      )
      XCTAssertEqual(
        receipt["effectiveLaunchManifestDigest"] as? String,
        request["effectiveLaunchManifestDigest"] as? String
      )
      XCTAssertEqual(receipt["launchProvenance"] as? String, "canonical_launcher")
      XCTAssertEqual(
        receipt["runtimeConfigSupplyMode"] as? String,
        "external_runtime_package"
      )
    }
  }

  func testIdempotentExplicitActivationPublishesExactActiveReceiptOverFailedLaunchReceipt() throws {
    let activeReceipt: [String: Any] = [
      "status": "activated",
      "requestDigest": canonicalDigest("a"),
      "validationIssues": [],
    ]
    let activeReceiptBefore = try canonicalJSONData(activeReceipt)
    var launchReceipt: [String: Any] = [
      "status": "failed",
      "requestDigest": canonicalDigest("9"),
      "validationIssues": ["runtime_config_activation_write_failed"],
    ]

    try NativeRuntimeConfigActivationCoordinator.publishAlreadyActivatedReceipt(
      activeReceipt,
      write: { receipt, name in
        XCTAssertEqual(name, "runtime-config-activation-receipt.json")
        launchReceipt = receipt
      }
    )

    XCTAssertEqual(try canonicalJSONData(launchReceipt), activeReceiptBefore)
    XCTAssertEqual(
      try canonicalJSONData(activeReceipt),
      activeReceiptBefore,
      "幂等显式 activation 只能复制已验证 active receipt，不得重写其身份"
    )
  }

  func testIdempotentExplicitActivationReceiptWriteFailureBlocksWithoutChangingActive() throws {
    let activeReceipt: [String: Any] = [
      "status": "activated",
      "requestDigest": canonicalDigest("b"),
      "validationIssues": [],
    ]
    let activeReceiptBefore = try canonicalJSONData(activeReceipt)
    let failedLaunchReceipt: [String: Any] = [
      "status": "failed",
      "requestDigest": canonicalDigest("8"),
      "validationIssues": ["runtime_config_activation_write_failed"],
    ]
    var launchReceipt = failedLaunchReceipt

    assertRuntimeConfigError(.activationReceiptWriteFailed) {
      try NativeRuntimeConfigActivationCoordinator.publishAlreadyActivatedReceipt(
        activeReceipt,
        write: { _, name in
          XCTAssertEqual(name, "runtime-config-activation-receipt.json")
          throw CocoaError(.fileWriteNoPermission)
        }
      )
    }

    XCTAssertEqual(try canonicalJSONData(activeReceipt), activeReceiptBefore)
    XCTAssertEqual(
      try canonicalJSONData(launchReceipt),
      try canonicalJSONData(failedLaunchReceipt)
    )
  }

  func testRuntimeActivationRestoresBothReceiptsWhenSecondaryWriteFails() throws {
    let previousActiveReceipt = Data("previous-active".utf8)
    let previousLaunchReceipt = Data("previous-launch".utf8)
    let names = [
      "runtime-config-active-receipt.json",
      "runtime-config-activation-receipt.json",
    ]
    let previous = [
      names[0]: previousActiveReceipt,
      names[1]: previousLaunchReceipt,
    ]
    var writes: [String] = []
    var restored: [String: Data] = [:]

    XCTAssertThrowsError(
      try NativeRuntimeConfigActivationCoordinator.commitActivationReceipts(
        ["status": "activated"],
        readExisting: { previous[$0] ?? nil },
        write: { _, name in
          writes.append(name)
          if name == names[1] {
            throw NativeRuntimeConfigReadError.activationReceiptWriteFailed
          }
        },
        restore: { data, name in
          if let data {
            restored[name] = data
          }
        }
      )
    ) { error in
      XCTAssertEqual(
        (error as? NativeRuntimeConfigReadError)?.flutterCode,
        NativeRuntimeConfigReadError.activationReceiptWriteFailed.flutterCode
      )
    }
    XCTAssertEqual(writes, names)
    XCTAssertEqual(restored[names[0]]!, previousActiveReceipt)
    XCTAssertEqual(restored[names[1]]!, previousLaunchReceipt)
  }

  func testRuntimeActivationReportsRollbackFailureWhenReceiptRestoreFails() throws {
    XCTAssertThrowsError(
      try NativeRuntimeConfigActivationCoordinator.commitActivationReceipts(
        ["status": "activated"],
        readExisting: { _ in Data("previous".utf8) },
        write: { _, name in
          if name == "runtime-config-activation-receipt.json" {
            throw NativeRuntimeConfigReadError.activationReceiptWriteFailed
          }
        },
        restore: { _, _ in
          throw NativeRuntimeConfigReadError.activationRollbackFailed
        }
      )
    ) { error in
      XCTAssertEqual(
        (error as? NativeRuntimeConfigReadError)?.flutterCode,
        NativeRuntimeConfigReadError.activationRollbackFailed.flutterCode
      )
    }
  }

  func testActiveReceiptAbsenceAndCorruptionAreReceiptSemantics() throws {
    try withPreservedRuntimeConfigFiles { directory in
      let receiptURL = directory.appendingPathComponent(
        "runtime-config-active-receipt.json",
        isDirectory: false
      )
      try? FileManager.default.removeItem(at: receiptURL)
      XCTAssertThrowsError(
        try NativeRuntimeConfigActivationCoordinator.readActiveReceiptDocument()
      ) { error in
        XCTAssertEqual(
          (error as? NativeRuntimeConfigReadError)?.flutterCode,
          "runtime_config_activation_receipt_missing"
        )
      }
      try Data("not-json".utf8).write(to: receiptURL)
      XCTAssertThrowsError(
        try NativeRuntimeConfigActivationCoordinator.readActiveReceiptDocument()
      ) { error in
        XCTAssertEqual(
          (error as? NativeRuntimeConfigReadError)?.flutterCode,
          "runtime_config_activation_receipt_malformed"
        )
      }
      try Data().write(to: receiptURL)
      XCTAssertThrowsError(
        try NativeRuntimeConfigActivationCoordinator.readActiveReceiptDocument()
      ) { error in
        XCTAssertEqual(
          (error as? NativeRuntimeConfigReadError)?.flutterCode,
          "runtime_config_activation_receipt_malformed"
        )
      }
    }
  }

  func testActivationFailureAppendsRollbackUnknownWhenActiveReadFails() throws {
    try withPreservedRuntimeConfigFiles { directory in
      let packageURL = directory.appendingPathComponent(
        "runtime-config-package.json",
        isDirectory: false
      )
      try Data("corrupted-active-package".utf8).write(to: packageURL)
      let digest = "sha256:" + String(repeating: "1", count: 64)

      let result = NativeRuntimeConfigActivationCoordinator.consumePendingActivationRequest(
        arguments: ["--qwq-runtime-config-activation-request-digest", digest],
        coldStartAllowed: true
      )

      XCTAssertTrue(result.requested)
      XCTAssertFalse(result.activated)
      XCTAssertNotEqual(
        result.errorCode,
        "runtime_config_activation_rollback_failed",
        "原始失败码不得被 rollback 状态未知标记覆盖"
      )
      XCTAssertTrue(
        result.validationIssues.contains("runtime_config_activation_rollback_failed"),
        "active digest 读取失败必须以 rollback_failed 标记状态未知，当前 issues=\(result.validationIssues)"
      )
    }
  }

  func testStaleWindowExemptionOnlyRelaxesExpiryForActivationIdentity() throws {
    let formatter = ISO8601DateFormatter()
    let afterExpiry = try XCTUnwrap(formatter.date(from: "2026-08-26T00:00:00Z"))
    let expired: [String: Any] = [
      "issuedAt": "2026-08-24T00:00:00Z",
      "expiresAt": "2026-08-25T00:00:00Z",
    ]

    // 消费路径：时间窗过期必须继续 fail-closed。
    XCTAssertThrowsError(
      try NativeRuntimeConfigStore.validateFreshness(expired, now: afterExpiry)
    ) { error in
      XCTAssertEqual(
        (error as? NativeRuntimeConfigReadError)?.flutterCode,
        "runtime_config_freshness_invalid"
      )
    }

    // 激活身份路径：豁免时间窗，过期旧包必须可被替换，不得死锁。
    XCTAssertNoThrow(
      try NativeRuntimeConfigStore.validateFreshness(
        expired,
        allowStaleIdentity: true,
        now: afterExpiry
      )
    )

    // 豁免不放松生命周期上限与结构校验。
    let overLifetime: [String: Any] = [
      "issuedAt": "2026-08-20T00:00:00Z",
      "expiresAt": "2026-08-25T00:00:00Z",
    ]
    XCTAssertThrowsError(
      try NativeRuntimeConfigStore.validateFreshness(
        overLifetime,
        allowStaleIdentity: true,
        now: afterExpiry
      )
    )
    let futureIssued: [String: Any] = [
      "issuedAt": "2026-08-27T00:00:00Z",
      "expiresAt": "2026-08-27T12:00:00Z",
    ]
    XCTAssertThrowsError(
      try NativeRuntimeConfigStore.validateFreshness(
        futureIssued,
        allowStaleIdentity: true,
        now: afterExpiry
      )
    )
    XCTAssertThrowsError(
      try NativeRuntimeConfigStore.validateFreshness(
        ["issuedAt": "2026-08-24T00:00:00Z"],
        allowStaleIdentity: true,
        now: afterExpiry
      )
    )
  }

  func testExplicitActivationAcceptsOnlySignedPreviousLayoutOfflinePredecessorBoundToReceipt() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()

    let active = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
      packageData: fixture.packageData,
      trust: fixture.trust,
      activeReceiptData: fixture.receiptData
    )

    XCTAssertEqual(active.packageDigest, fixture.packageDigest)
    XCTAssertEqual(active.trustEnvelopeDigest, fixture.trust.trustEnvelopeDigest)
    XCTAssertNil(active.package["rehearsalSpace"])
  }

  func testPreviousLayoutOfflinePredecessorRejectsShapeTrustSignatureAndReceiptDrift() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()

    var extraField = fixture.package
    extraField["unexpected"] = "field"
    assertRuntimeConfigError(.schemaMismatch) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: try canonicalJSONData(extraField),
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    }

    var currentShape = fixture.package
    currentShape["rehearsalSpace"] = [
      "mode": "standard",
      "snapshotDigest": canonicalDigest("9"),
      "instanceId": "default",
    ]
    assertRuntimeConfigError(.schemaMismatch) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: try canonicalJSONData(currentShape),
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    }

    let nonCanonicalData = try JSONSerialization.data(
      withJSONObject: fixture.package,
      options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    )
    assertRuntimeConfigError(.packageMalformed) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: nonCanonicalData,
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    }

    var sourceDrift = fixture.package
    sourceDrift["sourceGitSha"] = "not-a-git-sha"
    assertRuntimeConfigError(.sourceIdentityInvalid) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: try canonicalJSONData(sourceDrift),
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    }

    var contentSourceDrift = fixture.package
    contentSourceDrift["contentSource"] = "remote"
    assertRuntimeConfigError(.contentSourceMismatch) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: try canonicalJSONData(contentSourceDrift),
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    }

    var signatureDrift = fixture.package
    signatureDrift["signature"] = Data(repeating: 0, count: 64).base64EncodedString()
    assertRuntimeConfigError(.signatureInvalid) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: try canonicalJSONData(signatureDrift),
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    }

    var receiptDrift = fixture.receipt
    receiptDrift["packageDigest"] = canonicalDigest("8")
    assertRuntimeConfigError(.activationReceiptMismatch) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: fixture.packageData,
        trust: fixture.trust,
        activeReceiptData: try canonicalJSONData(receiptDrift)
      )
    }

    var trustDrift = fixture.trust.artifactTrustEnvelope
    trustDrift["buildProfile"] = "prod"
    let mismatchedTrust = NativeRuntimeConfigTrustProjection(
      artifactTrustEnvelope: trustDrift,
      trustEnvelopeDigest: fixture.trust.trustEnvelopeDigest,
      trustedPublicKeys: fixture.trust.trustedPublicKeys
    )
    assertRuntimeConfigError(.profileMismatch) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: fixture.packageData,
        trust: mismatchedTrust,
        activeReceiptData: fixture.receiptData
      )
    }
  }

  func testPreviousLayoutMigrationHistoryWritesCanonicalContentAddressedArchive() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "historical-migration-history-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    try NativeRuntimeConfigStore.archivePreviousLayoutMigrationHistory(
      packageData: fixture.packageData,
      receiptData: fixture.receiptData,
      packageDigest: fixture.packageDigest,
      baseDirectory: root
    )

    let digestHex = String(fixture.packageDigest.dropFirst("sha256:".count))
    let archive = root
      .appendingPathComponent("migration-history", isDirectory: true)
      .appendingPathComponent(digestHex, isDirectory: true)
    XCTAssertEqual(
      try Data(contentsOf: archive.appendingPathComponent("historical-package.json")),
      fixture.packageData
    )
    XCTAssertEqual(
      try Data(contentsOf: archive.appendingPathComponent("historical-active-receipt.json")),
      fixture.receiptData
    )
    let auditData = try Data(
      contentsOf: archive.appendingPathComponent("migration-audit.json")
    )
    let audit = try XCTUnwrap(
      JSONSerialization.jsonObject(with: auditData) as? [String: Any]
    )
    XCTAssertEqual(auditData, try canonicalJSONData(audit))
    XCTAssertEqual(audit["packageDigest"] as? String, fixture.packageDigest)
    XCTAssertEqual(
      audit["receiptDigest"] as? String,
      try dataDigest(fixture.receiptData)
    )
    XCTAssertEqual(Set(audit.keys), ["schema", "packageDigest", "receiptDigest"])
  }

  func testPreviousLayoutMigrationHistoryIsCreateOnceIdempotent() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "historical-migration-idempotent-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    for _ in 0..<2 {
      try NativeRuntimeConfigStore.archivePreviousLayoutMigrationHistory(
        packageData: fixture.packageData,
        receiptData: fixture.receiptData,
        packageDigest: fixture.packageDigest,
        baseDirectory: root
      )
    }
  }

  func testPreviousLayoutMigrationHistoryCollisionAndWriteFailureBlockBeforeActiveMutation() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "historical-migration-failure-\(UUID().uuidString)",
      isDirectory: true
    )
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    try NativeRuntimeConfigStore.archivePreviousLayoutMigrationHistory(
      packageData: fixture.packageData,
      receiptData: fixture.receiptData,
      packageDigest: fixture.packageDigest,
      baseDirectory: root
    )
    let activeBefore = fixture.packageData
    let digestHex = String(fixture.packageDigest.dropFirst("sha256:".count))
    let receiptArchive = root
      .appendingPathComponent("migration-history", isDirectory: true)
      .appendingPathComponent(digestHex, isDirectory: true)
      .appendingPathComponent("historical-active-receipt.json")
    try Data("collision".utf8).write(to: receiptArchive)

    assertRuntimeConfigError(.activationWriteFailed) {
      try NativeRuntimeConfigStore.archivePreviousLayoutMigrationHistory(
        packageData: fixture.packageData,
        receiptData: fixture.receiptData,
        packageDigest: fixture.packageDigest,
        baseDirectory: root
      )
    }
    XCTAssertEqual(activeBefore, fixture.packageData)

    var activeBytes = fixture.packageData
    assertRuntimeConfigError(.activationWriteFailed) {
      try NativeRuntimeConfigStore.archivePreviousLayoutMigrationHistory(
        packageData: fixture.packageData,
        receiptData: fixture.receiptData,
        packageDigest: fixture.packageDigest,
        baseDirectory: root,
        writeCreateOnce: { _, _ in
          throw NativeRuntimeConfigReadError.activationWriteFailed
        }
      )
      activeBytes = Data("candidate".utf8)
    }
    XCTAssertEqual(activeBytes, fixture.packageData, "归档失败必须发生在 active 替换前")
  }

  func testPreviousLayoutPredecessorRejectsNonCanonicalActiveReceiptBytes() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()
    let nonCanonicalReceipt = try JSONSerialization.data(
      withJSONObject: fixture.receipt,
      options: [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    )
    assertRuntimeConfigError(.activationReceiptMalformed) {
      _ = try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: fixture.packageData,
        trust: fixture.trust,
        activeReceiptData: nonCanonicalReceipt
      )
    }
  }

  func testRejectedPreviousLayoutPredecessorLeavesOriginalBytesUntouched() throws {
    let fixture = try previousLayoutOfflinePredecessorFixture()
    var invalid = fixture.package
    invalid["payloadDigest"] = canonicalDigest("7")
    let storedBytes = try canonicalJSONData(invalid)
    var activeBytes = storedBytes

    XCTAssertThrowsError(
      try NativeRuntimeConfigStore.validatePreviousLayoutOfflinePredecessor(
        packageData: activeBytes,
        trust: fixture.trust,
        activeReceiptData: fixture.receiptData
      )
    )

    XCTAssertEqual(activeBytes, storedBytes, "迁移校验失败不得改写或补齐旧 active")
    XCTAssertNil(
      try XCTUnwrap(JSONSerialization.jsonObject(with: activeBytes) as? [String: Any])[
        "rehearsalSpace"
      ]
    )
  }

  func testRecoveryContextDistinguishesFailureFromAbsence() throws {
    try withPreservedRuntimeConfigFiles { directory in
      let packageURL = directory.appendingPathComponent(
        "runtime-config-package.json",
        isDirectory: false
      )
      try? FileManager.default.removeItem(at: packageURL)
      switch NativeRuntimeConfigActivationCoordinator.readRecoveryRuntimeContext() {
      case .absent:
        break
      default:
        XCTFail("首装缺席必须是 typed absent，不得混入失败或空上下文")
      }

      try Data("corrupted-active-package".utf8).write(to: packageURL)
      switch NativeRuntimeConfigActivationCoordinator.readRecoveryRuntimeContext() {
      case .failure(let code):
        XCTAssertTrue(
          code.hasPrefix("runtime_config_"),
          "recovery context 读取失败必须携带登记错误码，当前 code=\(code)"
        )
      default:
        XCTFail("active package 读取失败必须返回 typed error，不得吞错为空上下文")
      }
    }
  }

  private func withPreservedRuntimeConfigFiles(_ body: (URL) throws -> Void) throws {
    let directory = try FileManager.default.url(
      for: .applicationSupportDirectory,
      in: .userDomainMask,
      appropriateFor: nil,
      create: true
    ).appendingPathComponent("qwq_runtime", isDirectory: true)
    try FileManager.default.createDirectory(
      at: directory,
      withIntermediateDirectories: true
    )
    let names = [
      "runtime-config-package.json",
      "runtime-config-active-receipt.json",
      "runtime-config-activation-receipt.json",
      "runtime-config-activation-request.json",
    ]
    var previous: [String: Data] = [:]
    for name in names {
      let url = directory.appendingPathComponent(name, isDirectory: false)
      previous[name] = FileManager.default.contents(atPath: url.path)
    }
    defer {
      for name in names {
        let url = directory.appendingPathComponent(name, isDirectory: false)
        try? FileManager.default.removeItem(at: url)
        if let data = previous[name] {
          try? data.write(to: url)
        }
      }
    }
    try body(directory)
  }

  private func runtimeConfigFileURL(_ name: String, in directory: URL) -> URL {
    directory.appendingPathComponent(name, isDirectory: false)
  }

  private func writeActivationRequest(
    _ request: [String: Any],
    in directory: URL
  ) throws -> String {
    let data = try JSONSerialization.data(
      withJSONObject: request,
      options: [.sortedKeys, .withoutEscapingSlashes]
    )
    try data.write(
      to: runtimeConfigFileURL(
        "runtime-config-activation-request.json",
        in: directory
      )
    )
    return "sha256:" + SHA256.hash(data: data).map {
      String(format: "%02x", $0)
    }.joined()
  }

  private func readRuntimeConfigReceipt(_ url: URL) throws -> [String: Any] {
    try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
    )
  }

  private func assertEmptyRuntimeConfigReceiptIdentity(
    _ receipt: [String: Any],
    file: StaticString = #filePath,
    line: UInt = #line
  ) {
    for field in [
      "environment",
      "buildProfile",
      "target",
      "launchProvenance",
      "runtimeConfigSupplyMode",
      "packageDigest",
      "trustEnvelopeDigest",
      "effectiveLaunchManifestDigest",
    ] {
      XCTAssertEqual(receipt[field] as? String, "", "field=\(field)", file: file, line: line)
    }
  }

  func testIncomingCallSecretsMigrateOutOfUserDefaults() throws {
    let suiteName = "rtc-push-\(UUID().uuidString)"
    let service = "rtc-push-test-\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      XCTFail("unable to create isolated UserDefaults")
      return
    }
    defer {
      defaults.removePersistentDomain(forName: suiteName)
    }
    let tokenKey = "qwq.rtc.apns_voip.active_token"
    let mutationKey = "qwq.rtc.push_endpoint.mutations"
    let token = "0123456789abcdef"
    let mutations = [[
      "mutationId": UUID().uuidString.lowercased(),
      "action": "upsert",
      "endpointKind": "apns_voip",
      "token": token,
      "occurredAt": ISO8601DateFormatter().string(from: Date()),
    ]]
    defaults.set(token, forKey: tokenKey)
    defaults.set(mutations, forKey: mutationKey)
    let keychain = IncomingCallKeychainStore(service: service)
    defer {
      keychain.remove(tokenKey)
      keychain.remove(mutationKey)
    }

    _ = IncomingCallPushCoordinator(
      defaults: defaults,
      secretStore: keychain
    )

    XCTAssertNil(defaults.string(forKey: tokenKey))
    XCTAssertNil(defaults.array(forKey: mutationKey))
    XCTAssertEqual(keychain.string(forKey: tokenKey), token)
    XCTAssertNotNil(keychain.data(forKey: mutationKey))
  }

  func testDeviceCalendarRequestValidatesCanonicalCrudShape() throws {
    let request = try XCTUnwrap(DeviceCalendarNativeRequest(
      operation: .create,
      arguments: eventArguments(idempotencyKey: "create-1")
    ))

    XCTAssertEqual(request.idempotencyKey, "create-1")
    XCTAssertEqual(request.title, "iOS 合同测试")
    XCTAssertEqual(request.timezone, "Asia/Shanghai")
    XCTAssertNil(DeviceCalendarNativeRequest(
      operation: .create,
      arguments: [
        "idempotencyKey": "create-1",
        "inputDigest": "invalid",
      ]
    ))
    XCTAssertNotNil(DeviceCalendarNativeRequest(
      operation: .delete,
      arguments: deleteArguments(
        idempotencyKey: "delete-1",
        eventId: "event-1"
      )
    ))
  }

  func testDeviceCalendarCreateUpdateDeleteAndReplayAreIdempotent() throws {
    let eventStore = EKEventStore()
    let suiteName = "device-calendar-\(UUID().uuidString.lowercased())"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    let plugin = AssistantDeviceActionPlugin(
      eventStore: eventStore,
      defaults: defaults
    )
    var eventIdentifier = ""
    defer {
      if let event = eventStore.event(withIdentifier: eventIdentifier) {
        try? eventStore.remove(event, span: .thisEvent, commit: true)
      }
      defaults.removePersistentDomain(forName: suiteName)
    }

    let create = eventArguments(
      idempotencyKey: "create-\(UUID().uuidString.lowercased())"
    )
    let first = invokeDeviceCalendar(
      plugin: plugin,
      method: "createEvent",
      arguments: create,
      label: "create calendar event"
    )
    XCTAssertEqual(first["status"] as? String, "succeeded")
    eventIdentifier = try XCTUnwrap(first["deviceEventId"] as? String)
    XCTAssertTrue(
      (first["receiptDigest"] as? String)?.hasPrefix("sha256:") ?? false
    )
    let created = try XCTUnwrap(
      eventStore.event(withIdentifier: eventIdentifier)
    )
    XCTAssertEqual(created.title, "iOS 合同测试")
    XCTAssertFalse(
      created.url?.absoluteString.contains(create["idempotencyKey"] as! String)
        ?? true
    )

    let restartedPlugin = AssistantDeviceActionPlugin(
      eventStore: eventStore,
      defaults: defaults
    )
    let createReplay = invokeDeviceCalendar(
      plugin: restartedPlugin,
      method: "createEvent",
      arguments: create,
      label: "replay calendar create"
    )
    XCTAssertEqual(createReplay["deviceEventId"] as? String, eventIdentifier)
    XCTAssertEqual(createReplay["replayed"] as? Bool, true)

    var update = eventArguments(
      idempotencyKey: "update-\(UUID().uuidString.lowercased())"
    )
    update["deviceEventId"] = eventIdentifier
    update["inputDigest"] = canonicalDigest("b")
    update["title"] = "iOS 合同测试（更新）"
    let updated = invokeDeviceCalendar(
      plugin: restartedPlugin,
      method: "updateEvent",
      arguments: update,
      label: "update calendar event"
    )
    XCTAssertEqual(updated["status"] as? String, "succeeded")
    XCTAssertEqual(
      eventStore.event(withIdentifier: eventIdentifier)?.title,
      "iOS 合同测试（更新）"
    )
    let updateReplay = invokeDeviceCalendar(
      plugin: restartedPlugin,
      method: "updateEvent",
      arguments: update,
      label: "replay calendar update"
    )
    XCTAssertEqual(updateReplay["replayed"] as? Bool, true)

    let delete = deleteArguments(
      idempotencyKey: "delete-\(UUID().uuidString.lowercased())",
      eventId: eventIdentifier
    )
    let deleted = invokeDeviceCalendar(
      plugin: restartedPlugin,
      method: "deleteEvent",
      arguments: delete,
      label: "delete calendar event"
    )
    XCTAssertEqual(deleted["status"] as? String, "succeeded")
    XCTAssertNil(eventStore.event(withIdentifier: eventIdentifier))
    let deleteReplay = invokeDeviceCalendar(
      plugin: restartedPlugin,
      method: "deleteEvent",
      arguments: delete,
      label: "replay calendar delete"
    )
    XCTAssertEqual(deleteReplay["status"] as? String, "succeeded")
    XCTAssertEqual(deleteReplay["replayed"] as? Bool, true)
  }

  private func invokeDeviceCalendar(
    plugin: AssistantDeviceActionPlugin,
    method: String,
    arguments: [String: Any],
    label: String
  ) -> [String: Any] {
    let completed = expectation(description: label)
    var response: [String: Any] = [:]
    plugin.handle(
      call: FlutterMethodCall(
        methodName: method,
        arguments: arguments
      )
    ) { value in
      response = value as? [String: Any] ?? [:]
      completed.fulfill()
    }
    wait(for: [completed], timeout: 5)
    return response
  }

  private func eventArguments(idempotencyKey: String) -> [String: Any] {
    let start = Date().addingTimeInterval(3_600)
    return [
      "idempotencyKey": idempotencyKey,
      "inputDigest": canonicalDigest("a"),
      "calendarId": "",
      "title": "iOS 合同测试",
      "startEpochMs": NSNumber(
        value: Int64(start.timeIntervalSince1970 * 1_000)
      ),
      "endEpochMs": NSNumber(
        value: Int64(start.addingTimeInterval(1_800).timeIntervalSince1970 * 1_000)
      ),
      "timezone": "Asia/Shanghai",
      "location": "西湖",
      "notes": "DeviceCalendar 原生合同",
    ]
  }

  private func deleteArguments(
    idempotencyKey: String,
    eventId: String
  ) -> [String: Any] {
    [
      "idempotencyKey": idempotencyKey,
      "inputDigest": canonicalDigest("c"),
      "deviceEventId": eventId,
    ]
  }

  private func assertRuntimeConfigError(
    _ expected: NativeRuntimeConfigReadError,
    file: StaticString = #filePath,
    line: UInt = #line,
    _ operation: () throws -> Void
  ) {
    XCTAssertThrowsError(try operation(), file: file, line: line) { error in
      XCTAssertEqual(
        (error as? NativeRuntimeConfigReadError)?.flutterCode,
        expected.flutterCode,
        file: file,
        line: line
      )
    }
  }

  private struct PreviousLayoutOfflinePredecessorFixture {
    let package: [String: Any]
    let packageData: Data
    let packageDigest: String
    let trust: NativeRuntimeConfigTrustProjection
    let receipt: [String: Any]
    let receiptData: Data
  }

  private func previousLayoutOfflinePredecessorFixture() throws
    -> PreviousLayoutOfflinePredecessorFixture
  {
    let privateKey = Curve25519.Signing.PrivateKey()
    let keyID = "historical-alpha-key"
    let encodedPublicKey = privateKey.publicKey.rawRepresentation.base64EncodedString()
    let trustDocument: [String: Any] = [
      "schema": AppLaunchContract.schemaValues["runtime_config_trust_envelope"]!,
      "buildProfile": "nonprod",
      "signatureAlgorithm": AppLaunchContract.runtimeConfigPackageSignatureAlgorithm,
      "trustedPublicKeys": [keyID: encodedPublicKey],
    ]
    let trustDigest = try canonicalJSONDigest(trustDocument)
    let trust = NativeRuntimeConfigTrustProjection(
      artifactTrustEnvelope: trustDocument,
      trustEnvelopeDigest: trustDigest,
      trustedPublicKeys: [keyID: encodedPublicKey]
    )
    var package: [String: Any] = [
      "schema": AppLaunchContract.schemaValues["offline_bootstrap_document"]!,
      "environment": "alpha",
      "buildProfile": "nonprod",
      "target": "alpha-local",
      "launchPolicy": "test_live",
      "contentSource": "bundled_snapshot",
      "sourceGitSha": String(repeating: "a", count: 40),
      "sourceTreeDigest": "sha256:" + String(repeating: "b", count: 64),
      "trustEnvelopeDigest": trustDigest,
      "runtime": ["appRuntimeEnv": "alpha"],
      "payloadDigest": "",
      "signatureAlgorithm": AppLaunchContract.runtimeConfigPackageSignatureAlgorithm,
      "signatureKeyId": keyID,
      "trustedPublicKeys": [keyID: encodedPublicKey],
      "signature": "",
    ]
    var payloadDocument = package
    payloadDocument.removeValue(forKey: "signature")
    package["payloadDigest"] = try canonicalJSONDigest(payloadDocument)
    var signedPayload = package
    signedPayload.removeValue(forKey: "signature")
    package["signature"] = try privateKey.signature(
      for: canonicalJSONData(signedPayload)
    ).base64EncodedString()
    let packageData = try canonicalJSONData(package)
    let packageDigest = try canonicalJSONDigest(package)
    let receipt: [String: Any] = [
      "schema": AppLaunchContract.schemaValues["runtime_config_activation_receipt"]!,
      "status": AppLaunchContract.runtimeConfigActivationReceiptStatuses[0],
      "requestDigest": canonicalDigest("1"),
      "environment": "alpha",
      "buildProfile": "nonprod",
      "target": "alpha-local",
      "launchProvenance": "canonical_launcher",
      "runtimeConfigSupplyMode": "build_time_self_supply",
      "packageDigest": packageDigest,
      "trustEnvelopeDigest": trustDigest,
      "effectiveLaunchManifestDigest": canonicalDigest("2"),
      "previousActiveDigest": "",
      "activePackageDigest": packageDigest,
      "errorCode": "",
      "validationIssues": [],
    ]
    return PreviousLayoutOfflinePredecessorFixture(
      package: package,
      packageData: packageData,
      packageDigest: packageDigest,
      trust: trust,
      receipt: receipt,
      receiptData: try canonicalJSONData(receipt)
    )
  }

  private func canonicalJSONData(_ document: [String: Any]) throws -> Data {
    try NativeRuntimeCanonicalJSON.data(document)
  }

  private func dataDigest(_ data: Data) throws -> String {
    "sha256:" + SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
  }

  private func canonicalRuntimeValues(environment: String) -> [String: Any] {
    [
      "appRuntimeEnv": environment,
      "gatewayBaseUrl": "https://api.quwoquan.example",
      "legalBaseUrl": "https://legal.quwoquan.example",
      "publicWebBaseUrl": "https://www.quwoquan.example",
      "appDownloadBaseUrl": "https://download.quwoquan.example",
      "realtimeBaseUrl": "wss://realtime.quwoquan.example",
      "mediaAvatarCdnBaseUrl": "https://avatar.quwoquan.example",
      "mediaImageCdnBaseUrl": "https://image.quwoquan.example",
      "mediaVideoCdnBaseUrl": "https://video.quwoquan.example",
      "mediaUploadBaseUrl": "https://upload.quwoquan.example",
      "rtcMediaConnectionUrl": "wss://rtc.quwoquan.example",
    ]
  }

  private func effectiveLaunchManifest(
    environment: String,
    buildProfile: String,
    target: String,
    launchPolicy: String,
    requiresLocalTransport: Bool,
    transportRequired: Bool
  ) -> [String: Any] {
    [
      "schema": AppLaunchContract.schemaValues["app_effective_launch_manifest"]!,
      "environment": environment,
      "buildProfile": buildProfile,
      "target": target,
      "entrypoint": AppLaunchContract.appEffectiveLaunchManifestEntrypoint["remote"]!,
      "launchProvenance": "canonical_launcher",
      "runtimeConfigSupplyMode": "external_runtime_package",
      "launchPolicy": launchPolicy,
      "runtimeConfigPackageDigest": canonicalDigest("a"),
      "runtimeConfigTrustEnvelopeDigest": canonicalDigest("b"),
      "requiresLocalTransport": requiresLocalTransport,
      "transport": [
        "required": transportRequired,
        "reverseExpectedPorts": transportRequired ? "443,8443" : "",
        "reverseActualPorts": transportRequired ? "8443,443" : "",
        "reverseReceiptDigest": transportRequired ? canonicalDigest("c") : "",
        "consumerLeaseId": transportRequired ? canonicalDigest("d") : "",
      ],
    ]
  }

  private func activationRequest(
    manifest: [String: Any],
    environment: String = "alpha",
    buildProfile: String = "nonprod",
    target: String = "alpha-local",
    launchPolicy: String = "test_live"
  ) throws -> [String: Any] {
    [
      "schema": AppLaunchContract.schemaValues["runtime_config_activation_request"]!,
      "environment": environment,
      "buildProfile": buildProfile,
      "target": target,
      "package": [
        "environment": environment,
        "buildProfile": buildProfile,
        "target": target,
        "launchPolicy": launchPolicy,
      ],
      "packageDigest": canonicalDigest("a"),
      "trustEnvelopeDigest": canonicalDigest("b"),
      "effectiveLaunchManifest": manifest,
      "effectiveLaunchManifestDigest": try canonicalJSONDigest(manifest),
      "expectedActiveDigest": "",
    ]
  }

  private func canonicalJSONDigest(_ document: [String: Any]) throws -> String {
    let data = try JSONSerialization.data(
      withJSONObject: document,
      options: [.sortedKeys, .withoutEscapingSlashes]
    )
    return "sha256:" + SHA256.hash(data: data).map {
      String(format: "%02x", $0)
    }.joined()
  }

  private func canonicalDigest(_ character: Character) -> String {
    "sha256:" + String(repeating: String(character), count: 64)
  }

}
