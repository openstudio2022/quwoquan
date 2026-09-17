#if targetEnvironment(simulator) && QWQ_EXTERNAL_UAT_BROKER
import CryptoKit
import Darwin
import Flutter
import Foundation

/// GWT-008 Simulator-only external-AUT relay。授权材料只驻内存。
final class AlphaGwt008NativeEvidenceDriver {
  static let channel = "quwoquan/alpha_rehearsal/native_evidence"
  static let appGroupIdentifier = "group.com.leadwise.quwoquan.alpha.uat"
  enum Failure: Error, Equatable { case typed(String) }

  private let processId: pid_t
  private let startedUptime: TimeInterval
  private let now: () -> TimeInterval
  private let queue = DispatchQueue(label: "quwoquan.alpha.gwt008.broker")
  private var admission: [String: Any]?
  private var verifier: Data?
  private var sealed: [String: Any]?
  private var sealedDigest = ""
  private var socketPath: String?
  private var listenFd: Int32 = -1
  private var revoked = false
  private var queried = false
  private var expectedLauncherPid: pid_t = 0

  init(
    processId: pid_t = getpid(),
    startedUptime: TimeInterval = ProcessInfo.processInfo.systemUptime,
    now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
  ) {
    self.processId = processId
    self.startedUptime = startedUptime
    self.now = now
  }

  deinit { cleanupSocket() }

  func register(binaryMessenger: FlutterBinaryMessenger) {
    let methodChannel = FlutterMethodChannel(name: Self.channel, binaryMessenger: binaryMessenger)
    methodChannel.setMethodCallHandler { [weak self] call, result in
      guard let self else { result(FlutterMethodNotImplemented); return }
      do {
        let arguments = call.arguments as? [String: Any] ?? [:]
        switch call.method {
        case "bindStartupObservation", "readProcessObservation":
          result(try self.processObservation(attemptId: arguments["launchAttemptId"] as? String ?? ""))
        case "requireObservationAdmission":
          try self.requireObservationAdmission(arguments)
          result(nil)
        case "recordRedactedInput":
          result(try self.redactedInputObservation(arguments))
        case "sealObservation":
          result(try self.sealObservation(arguments))
        default:
          result(FlutterMethodNotImplemented)
        }
      } catch let error as Failure {
        result(FlutterError(code: {
          if case .typed(let code) = error { return code }
          return "APP.UAT.relay_contract_drift"
        }(), message: nil, details: nil))
      } catch {
        result(FlutterError(code: "APP.UAT.relay_contract_drift", message: nil, details: nil))
      }
    }
  }

  func startUATBroker(
    socketDirectory: URL? = nil,
    randomComponent: String = UUID().uuidString.lowercased()
  ) throws -> String {
    return try queue.sync {
      if socketDirectory == nil {
        let environment = ProcessInfo.processInfo.environment
        guard
          let launcher = environment["QWQ_UAT_LAUNCHER_PID"], Int32(launcher) != nil,
          let attempt = environment["QWQ_UAT_HOST_ATTEMPT"], !attempt.isEmpty,
          let digest = environment["QWQ_UAT_CONTROL_DIGEST"],
          digest.range(of: "^sha256:[0-9a-f]{64}$", options: .regularExpression) != nil
        else { throw Failure.typed("APP.UAT.relay_admission_mismatch") }
        expectedLauncherPid = Int32(launcher)!
      }
      return try openSocket(directory: socketDirectory ?? Self.appGroupDirectory(), randomComponent: randomComponent)
    }
  }

  func arm(
    admission: [String: Any],
    verifierHex: String,
    launcherPid: pid_t,
    socketDirectory: URL,
    randomComponent: String = UUID().uuidString.lowercased()
  ) throws -> String {
    return try queue.sync {
      try storeAdmission(admission, verifierHex: verifierHex, launcherPid: launcherPid)
      if socketPath == nil {
        _ = try openSocket(directory: socketDirectory, randomComponent: randomComponent)
      }
      return socketPath!
    }
  }

  func sealObservation(_ input: [String: Any]) throws -> String {
    return try queue.sync {
      try requireArmed()
      if input["processId"] != nil || input["sealedAtMonotonicMs"] != nil {
        throw Failure.typed("APP.UAT.relay_contract_drift")
      }
      try rejectSensitive(input)
      let nowMs = monotonicMs()
      let admittedAt = int64(admission!["admittedAtMonotonicMs"])
      let expiresAt = int64(admission!["expiresAtMonotonicMs"])
      if nowMs < admittedAt || nowMs > expiresAt {
        throw Failure.typed("APP.UAT.relay_scope_mismatch")
      }
      var snapshot = input
      snapshot["schema"] = "external-uat-sealed-snapshot"
      snapshot["processId"] = processId
      snapshot["sealedAtMonotonicMs"] = nowMs
      snapshot.removeValue(forKey: "snapshotDigest")
      try rejectSensitive(snapshot)
      let digest = try canonicalDigest(snapshot)
      if let sealed, !sealedDigest.isEmpty {
        if try canonicalDigest(sealed.filter { $0.key != "snapshotDigest" }) == digest {
          return sealedDigest
        }
        throw Failure.typed("APP.UAT.relay_snapshot_conflict")
      }
      snapshot["snapshotDigest"] = digest
      sealed = snapshot
      sealedDigest = digest
      return digest
    }
  }

  func query(_ frame: [String: Any], peerPid: pid_t, peerEuid: uid_t) throws -> [String: Any] {
    return try queue.sync {
      try requireArmed()
      if queried { throw Failure.typed("APP.UAT.relay_consumed") }
      if revoked { throw Failure.typed("APP.UAT.relay_revoked") }
      guard let sealed, !sealedDigest.isEmpty else { throw Failure.typed("APP.UAT.relay_not_sealed") }
      if peerPid != expectedLauncherPid || peerEuid != geteuid() {
        throw Failure.typed("APP.UAT.relay_peer_rejected")
      }
      let sealedAt = int64(sealed["sealedAtMonotonicMs"])
      if monotonicMs() >= sealedAt + 60_000 {
        throw Failure.typed("APP.UAT.relay_expired")
      }
      try verifyMac(frame)
      queried = true
      revoked = true
      cleanupSecrets()
      var result: [String: Any] = [
        "schema": "external-uat-broker-result",
        "status": "observed",
        "admissionDigest": admission!["admissionDigest"] as Any,
        "terminalDigest": frame["terminalDigest"] as Any,
        "snapshot": sealed,
        "snapshotDigest": sealedDigest,
        "consumed": true,
        "revoked": true,
        "errorCode": "",
      ]
      result["resultDigest"] = try canonicalDigest(result)
      return result
    }
  }

  func processObservation(attemptId: String) throws -> [String: Any] {
    if attemptId.isEmpty { throw Failure.typed("APP.UAT.relay_scope_mismatch") }
    return [
      "processId": processId,
      "launchAttemptId": attemptId,
      "processStartedAtMonotonicMs": Int64((startedUptime * 1000).rounded()),
    ]
  }

  func redactedInputObservation(_ input: [String: Any]) throws -> [String: Any] {
    try rejectSensitive(input)
    return ["observed": "input-redacted"]
  }

  func revoke() {
    queue.sync {
      revoked = true
      queried = true
      cleanupSecrets()
      cleanupSocket()
    }
  }

  private func requireObservationAdmission(_ arguments: [String: Any]) throws {
    try requireArmed()
    if string(arguments["launchAttemptId"]) != string(admission!["launchAttemptId"])
      || string(arguments["caseId"]) != string(admission!["caseId"])
      || int64(arguments["generation"]) != int64(admission!["generation"])
      || string(arguments["observationBinding"]) != string(admission!["observationBinding"])
    {
      throw Failure.typed("APP.UAT.relay_scope_mismatch")
    }
  }

  private func storeAdmission(_ raw: [String: Any], verifierHex: String, launcherPid: pid_t) throws {
    if revoked || admission != nil { throw Failure.typed("APP.UAT.relay_stale") }
    if raw["schema"] as? String != "external-uat-managed-launch-admission" {
      throw Failure.typed("APP.UAT.relay_admission_mismatch")
    }
    var body = raw
    let declared = string(body.removeValue(forKey: "admissionDigest"))
    if try canonicalDigest(body) != declared {
      throw Failure.typed("APP.UAT.relay_admission_mismatch")
    }
    if int64(raw["processId"]) != Int64(processId) {
      throw Failure.typed("APP.UAT.relay_scope_mismatch")
    }
    if monotonicMs() >= int64(raw["expiresAtMonotonicMs"]) {
      throw Failure.typed("APP.UAT.relay_stale")
    }
    guard
      verifierHex.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
      let secret = Data(hex: verifierHex), secret.count == 32
    else { throw Failure.typed("APP.UAT.relay_contract_drift") }
    admission = raw
    verifier = secret
    expectedLauncherPid = launcherPid
    queried = false
    revoked = false
  }

  private func requireArmed() throws {
    if revoked { throw Failure.typed("APP.UAT.relay_revoked") }
    if admission == nil || verifier == nil { throw Failure.typed("APP.UAT.relay_admission_mismatch") }
  }

  private func verifyMac(_ frame: [String: Any]) throws {
    guard let verifier else { throw Failure.typed("APP.UAT.relay_admission_mismatch") }
    var unsigned = frame
    let mac = string(unsigned.removeValue(forKey: "mac"))
    let expected = HMAC<SHA256>.authenticationCode(
      for: try canonicalBytes(unsigned),
      using: SymmetricKey(data: verifier)
    )
    let actual = expected.map { String(format: "%02x", $0) }.joined()
    if mac != actual { throw Failure.typed("APP.UAT.relay_mac_invalid") }
    if string(frame["admissionDigest"]) != string(admission!["admissionDigest"])
      || int64(frame["processId"]) != Int64(processId)
      || string(frame["caseId"]) != string(admission!["caseId"])
    {
      throw Failure.typed("APP.UAT.relay_scope_mismatch")
    }
  }

  private func openSocket(directory: URL, randomComponent: String) throws -> String {
    if listenFd >= 0 || socketPath != nil { throw Failure.typed("APP.UAT.relay_stale") }
    guard randomComponent.range(of: "^[a-z0-9-]{16,64}$", options: .regularExpression) != nil else {
      throw Failure.typed("APP.UAT.relay_contract_drift")
    }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    let path = directory.appendingPathComponent("gwt008-\(processId)-\(randomComponent).sock").path
    unlink(path)
    listenFd = socket(AF_UNIX, SOCK_STREAM, 0)
    if listenFd < 0 { throw Failure.typed("APP.UAT.relay_process_died") }
    var address = sockaddr_un()
    address.sun_family = sa_family_t(AF_UNIX)
    let copied = path.withCString { source in
      withUnsafeMutableBytes(of: &address.sun_path) { destination -> Bool in
        guard let base = destination.baseAddress, destination.count > path.utf8.count else {
          return false
        }
        strncpy(base.assumingMemoryBound(to: CChar.self), source, destination.count - 1)
        return true
      }
    }
    if !copied {
      cleanupSocket()
      throw Failure.typed("APP.UAT.relay_contract_drift")
    }
    let bindResult = withUnsafePointer(to: &address) {
      $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
        bind(listenFd, $0, socklen_t(MemoryLayout<sockaddr_un>.size))
      }
    }
    if bindResult != 0 || listen(listenFd, 2) != 0 || chmod(path, 0o600) != 0 {
      cleanupSocket()
      throw Failure.typed("APP.UAT.relay_process_died")
    }
    socketPath = path
    acceptLoop()
    return path
  }

  private func acceptLoop() {
    let fd = listenFd
    DispatchQueue.global(qos: .userInitiated).async { [weak self] in
      while let self, fd >= 0, self.listenFd == fd {
        var address = sockaddr_un()
        var length = socklen_t(MemoryLayout<sockaddr_un>.size)
        let client = withUnsafeMutablePointer(to: &address) {
          $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            accept(fd, $0, &length)
          }
        }
        if client < 0 { break }
        self.handleClient(client)
      }
    }
  }

  private func handleClient(_ client: Int32) {
    defer { close(client) }
    var incoming = Data()
    var buffer = [UInt8](repeating: 0, count: 8192)
    while incoming.count <= 256 * 1024 {
      let readCount = read(client, &buffer, buffer.count)
      if readCount <= 0 { return }
      incoming.append(buffer, count: readCount)
      if incoming.contains(0x0A) { break }
    }
    guard let line = incoming.split(separator: 0x0A, maxSplits: 1, omittingEmptySubsequences: false).first,
          let frame = try? JSONSerialization.jsonObject(with: Data(line)) as? [String: Any]
    else { return }
    let response: [String: Any]
    do {
      if frame["operation"] as? String == "armRelay" {
        let admission = frame["admission"] as? [String: Any] ?? [:]
        try storeAdmission(
          admission,
          verifierHex: string(frame["verifier"]),
          launcherPid: expectedLauncherPid == 0 ? getpid() : expectedLauncherPid
        )
        response = [:]
      } else {
        var peerPid: pid_t = 0
        var pidLength = socklen_t(MemoryLayout<pid_t>.size)
        _ = getsockopt(client, 0, 2, &peerPid, &pidLength)
        response = try query(
          frame,
          peerPid: peerPid == 0 ? expectedLauncherPid : peerPid,
          peerEuid: geteuid()
        )
      }
    } catch let error as Failure {
      if case .typed(let code) = error {
        response = ["errorCode": code]
      } else {
        response = ["errorCode": "APP.UAT.relay_contract_drift"]
      }
    } catch {
      response = ["errorCode": "APP.UAT.relay_contract_drift"]
    }
    if let data = try? JSONSerialization.data(withJSONObject: response, options: [.sortedKeys, .withoutEscapingSlashes]) {
      var payload = data
      payload.append(0x0A)
      _ = payload.withUnsafeBytes { write(client, $0.baseAddress, payload.count) }
    }
  }

  private func cleanupSecrets() {
    guard var secret = verifier else { return }
    secret.resetBytes(in: 0..<secret.count)
    verifier = secret
    verifier = nil
  }

  private func cleanupSocket() {
    if let socketPath { unlink(socketPath) }
    if listenFd >= 0 { close(listenFd) }
    listenFd = -1
    socketPath = nil
  }

  private func monotonicMs() -> Int64 { Int64((now() * 1000).rounded()) }

  private func rejectSensitive(_ value: [String: Any]) throws {
    let keys = value.keys.map { $0.lowercased() }
    if keys.contains(where: { ["phone", "otp", "identity", "account", "challenge", "payload", "secret", "mac", "capability"].contains($0) }) {
      throw Failure.typed("APP.UAT.relay_sensitive_field")
    }
  }

  private func canonicalBytes(_ value: [String: Any]) throws -> Data {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
  }

  private func canonicalDigest(_ value: [String: Any]) throws -> String {
    let hash = SHA256.hash(data: try canonicalBytes(value))
    return "sha256:" + hash.map { String(format: "%02x", $0) }.joined()
  }

  private func string(_ value: Any?) -> String { value as? String ?? "" }

  private func int64(_ value: Any?) -> Int64 {
    if let number = value as? NSNumber { return number.int64Value }
    if let value = value as? Int64 { return value }
    if let value = value as? Int { return Int64(value) }
    return 0
  }

  private static func appGroupDirectory() throws -> URL {
    guard let root = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupIdentifier) else {
      throw Failure.typed("APP.UAT.relay_peer_rejected")
    }
    return root
  }
}

private extension Data {
  init?(hex: String) {
    let scalars = Array(hex.utf8)
    guard scalars.count.isMultiple(of: 2) else { return nil }
    var bytes = [UInt8]()
    bytes.reserveCapacity(scalars.count / 2)
    var index = scalars.startIndex
    while index < scalars.endIndex {
      let next = scalars.index(index, offsetBy: 2)
      guard let value = UInt8(String(bytes: scalars[index..<next], encoding: .utf8) ?? "", radix: 16) else {
        return nil
      }
      bytes.append(value)
      index = next
    }
    self.init(bytes)
  }
}
#endif
