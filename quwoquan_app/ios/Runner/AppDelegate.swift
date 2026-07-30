import AVFoundation
import CoreFoundation
import CoreTelephony
import CoreGraphics
import CoreLocation
import CryptoKit
import Foundation
import Flutter
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
    let manifest = nativeRuntimeIdentityManifest
    let environment = manifest["runtimeEnvironment"] as? String ?? "unknown"
    let configDigest = manifest["runtimeConfigDigest"] as? String ?? "missing"
    let definesDigest = manifest["dartDefinesDigest"] as? String ?? "missing"
    let target = manifest["launchTarget"] as? String ?? "missing"
    let effectiveDigest =
      manifest["effectiveLaunchManifestDigest"] as? String ?? "missing"
    return
      "\(currentBuild)|\(environment)|\(configDigest)|\(definesDigest)|\(target)|\(effectiveDigest)"
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
    nativeRuntimeIdentityManifest["effectiveLaunchManifestDigest"] as? String ?? ""
  }

  private static func clearFatalMarker(reason: String) {
    UserDefaults.standard.removeObject(forKey: startupHealthFatalBuildKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalAtKey)
    UserDefaults.standard.removeObject(forKey: startupHealthFatalQueuedIdentityKey)
    CFPreferencesAppSynchronize(kCFPreferencesCurrentApplication)
    NSLog("QWQStartup startup_fatal_marker_stale_cleared reason=%@", reason)
  }

  private static var nativeRuntimeIdentityManifest: [String: Any] {
    guard
      let url = Bundle.main.url(
        forResource: "QWQNativeRuntime",
        withExtension: "plist"
      ),
      let data = try? Data(contentsOf: url),
      let raw = try? PropertyListSerialization.propertyList(
        from: data,
        options: [],
        format: nil
      ),
      let manifest = raw as? [String: Any]
    else {
      return [:]
    }
    return manifest
  }
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
    recoverySurface: String = "",
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
  private var recoveryExternalOpenInFlight = false
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
    guard confirmedPreviousBuildFatal else {
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
    guard !confirmedPreviousBuildFatal else {
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

  private func registerMethodChannels(
    binaryMessenger: FlutterBinaryMessenger,
    includeStartupTimings: Bool = true
  ) {
    if includeStartupTimings {
      registerStartupTimingsChannel(binaryMessenger: binaryMessenger)
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
          "recoveryBaseUrl": self.recoveryBaseURLString,
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
    let bundleValues = [
      Bundle.main.object(forInfoDictionaryKey: "QWQRecoveryBaseURL") as? String,
      Bundle.main.object(forInfoDictionaryKey: "QWQPublicWebURL") as? String,
      Bundle.main.object(forInfoDictionaryKey: "QWQAppDownloadBaseURL") as? String,
    ]
    return (manifestValues + bundleValues).compactMap { rawValue in
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
      guard call.method == "readProcessSegments" else {
        result(FlutterMethodNotImplemented)
        return
      }
      let elapsedMs = Int(
        (ProcessInfo.processInfo.systemUptime - self.processStartUptime) * 1000
      )
      result([
        "elapsedSinceProcessStartMs": elapsedMs,
        "deadlineOrigin": "ios_process",
        "startupAttemptId": self.startupTelemetryJournal.currentAttemptId,
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
      currentDartAttemptId = safeStartupIdentifier(event["attemptId"] as? String)
      currentLaunchMode = safeStartupEnum(event["launchMode"] as? String)
      let hotRestart = dartStartupAttemptStarted
      dartStartupAttemptStarted = true
      currentDartAttemptIsHotRestart = hotRestart
      currentDartAttemptStartedUptime = hotRestart
        ? ProcessInfo.processInfo.systemUptime
        : processStartUptime
      let configurationState = safeStartupEnum(
        event["configurationState"] as? String
      )
      let missingDefineKeys = safeDefineKeyList(event["missingDefineKeys"] as? String)
      NSLog(
        "QWQStartup ios_dart_startup_attempt attemptId=%@ launchMode=%@ hotRestart=%@ configurationState=%@ effectiveLaunchManifestDigest=%@%@",
        currentDartAttemptId,
        currentLaunchMode,
        hotRestart ? "true" : "false",
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
    if !confirmedPreviousBuildFatal {
      super.applicationDidBecomeActive(application)
    }
    if !appInForeground {
      appInForeground = true
      foregroundStartedUptime = ProcessInfo.processInfo.systemUptime
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
    if !confirmedPreviousBuildFatal {
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
    if !confirmedPreviousBuildFatal {
      super.applicationWillResignActive(application)
    }
  }

  override func applicationWillTerminate(_ application: UIApplication) {
    cancelFlutterFirstFrameWatchdog()
    cancelNativeRecoveryTerminalReconciliation()
    if !confirmedPreviousBuildFatal {
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
      recoverySurface: "native_recovery",
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
    guard (!startupSafeTerminalConfirmed || confirmedPreviousBuildFatal),
          !nativeRecoveryShown,
          let window
    else { return }
    nativeRecoveryShown = true

    let recovery = UIView(frame: window.bounds)
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
    configureRecoveryButton(primary, title: "正在检查…", filled: true, enabled: false)

    let web = RecoveryActionButton(type: .system)
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
    if let value = nativeRuntimeManifest["recoveryBaseURL"] as? String,
       isTrustedRecoveryURL(URL(string: value)) {
      return value
    }
    let configured = Bundle.main.object(forInfoDictionaryKey: "QWQRecoveryBaseURL") as? String
    let value = configured?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if isTrustedRecoveryURL(URL(string: value)) {
      return value
    }
    return ""
  }

  private var publicWebURLString: String {
    if let value = nativeRuntimeManifest["publicWebURL"] as? String,
       isTrustedRecoveryURL(URL(string: value)) {
      return value
    }
    let configured = Bundle.main.object(forInfoDictionaryKey: "QWQPublicWebURL") as? String
    let value = configured?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if isTrustedRecoveryURL(URL(string: value)) {
      return value
    }
    return ""
  }

  private var appDownloadBaseURLString: String {
    if let value = nativeRuntimeManifest["appDownloadBaseURL"] as? String,
       isTrustedRecoveryURL(URL(string: value)) {
      return value
    }
    let configured = Bundle.main.object(
      forInfoDictionaryKey: "QWQAppDownloadBaseURL"
    ) as? String
    let value = configured?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if isTrustedRecoveryURL(URL(string: value)) {
      return value
    }
    return ""
  }

  private var nativeRuntimeEnvironment: String {
    if let value = nativeRuntimeManifest["runtimeEnvironment"] as? String,
       ["alpha", "beta", "gamma", "prod"].contains(value) {
      return value
    }
    let configured = Bundle.main.object(forInfoDictionaryKey: "QWQRuntimeEnvironment") as? String
    let value = configured?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return ["alpha", "beta", "gamma", "prod"].contains(value) ? value : "prod"
  }

  private var nativeRuntimeManifest: [String: Any] {
    guard
      let url = Bundle.main.url(
        forResource: "QWQNativeRuntime",
        withExtension: "plist"
      ),
      let data = try? Data(contentsOf: url),
      let value = try? PropertyListSerialization.propertyList(
        from: data,
        options: [],
        format: nil
      ) as? [String: Any]
    else {
      return [:]
    }
    return value
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
    UIApplication.shared.open(url, options: [:], completionHandler: completion)
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
