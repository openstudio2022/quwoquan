import AVFoundation
import CoreFoundation
import CoreTelephony
import CoreGraphics
import CoreLocation
import Foundation
import Flutter
import MetricKit
import PushKit
import UIKit

/// 仅持久化已脱敏的原生未捕获异常类别，供下次 Dart 启动产出一条标准诊断事实。
/// 原生异常消息与堆栈绝不能写入 UserDefaults 或运行时日志管道。
private let nativeCrashMarkerKindKey = "qwq.runtime.previous_native_crash_kind"
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
    guard let kind = UserDefaults.standard.string(forKey: nativeCrashMarkerKindKey),
          !kind.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else {
      return nil
    }
    UserDefaults.standard.removeObject(forKey: nativeCrashMarkerKindKey)
    return ["kind": kind]
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

/// 首帧前只落固定 schema 到本地，不做网络 IO，也不记录账号、异常文本或堆栈。
///
/// Flutter 成功装配后会从同一 UserDefaults 迁入可靠启动 journal；下一次成功启动会补传
/// 本次 native watchdog 的终态。
private final class StartupNativeTelemetryJournal {
  private static let eventsKey = "startup_telemetry_native_journal"
  private static let attemptKey = "startup_telemetry_native_attempt"
  private static let maxEvents = 32

  private let defaults: UserDefaults
  private var attemptId = ""
  private var sequence = 0
  private var lastElapsedMs = 0

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    beginAttempt()
  }

  func beginAttempt() {
    attemptId = UUID().uuidString.replacingOccurrences(of: "-", with: "")
    sequence = 0
    lastElapsedMs = 0
    defaults.set(attemptId, forKey: Self.attemptKey)
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
    sequence += 1
    let normalizedElapsedMs = max(0, elapsedMs)
    let phaseDurationMs = max(0, normalizedElapsedMs - lastElapsedMs)
    lastElapsedMs = max(lastElapsedMs, normalizedElapsedMs)
    var event: [String: Any] = [
      "eventId": "\(attemptId)_\(sequence)",
      "attemptId": attemptId,
      "sequence": sequence,
      "phase": phase,
      "phaseDurationMs": phaseDurationMs,
      "elapsedMs": normalizedElapsedMs,
      "outcome": outcome,
      "occurredAt": ISO8601DateFormatter().string(from: Date()),
      "platform": "ios",
      "runtimeEnv": "unknown",
    ]
    if !recoverySurface.isEmpty {
      event["recoverySurface"] = recoverySurface
    }
    if !failureCode.isEmpty {
      event["failureCode"] = failureCode
    }
    if !failureSource.isEmpty {
      event["failureSource"] = failureSource
    }
    if !deadlineOrigin.isEmpty {
      event["deadlineOrigin"] = deadlineOrigin
    }
    guard let data = try? JSONSerialization.data(withJSONObject: event),
          let encoded = String(data: data, encoding: .utf8)
    else {
      return
    }
    var events = defaults.stringArray(forKey: Self.eventsKey) ?? []
    events.append(encoded)
    if events.count > Self.maxEvents {
      events.removeFirst(events.count - Self.maxEvents)
    }
    defaults.set(events, forKey: Self.eventsKey)
  }

  var currentAttemptId: String { attemptId }

  func events() -> [String] {
    defaults.stringArray(forKey: Self.eventsKey) ?? []
  }

  func clearEvents() {
    defaults.removeObject(forKey: Self.eventsKey)
  }
}

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  // 所有构建都使用同一进程钟硬门；Debug 慢启动必须修关键路径，不能形成双时钟。
  private static let flutterFirstFrameDeadline: TimeInterval = 6
  private let processStartUptime = ProcessInfo.processInfo.systemUptime
  private let videoEditingPlugin = VideoEditingPlugin()
  private let personalAssistantNativeApiPlugin = PersonalAssistantNativeApiPlugin()
  private let commercialAuthPlugin = CommercialAuthPlugin()
  private let aliyunOneTapPlugin = AliyunOneTapPlugin()
  let incomingCallPushCoordinator = IncomingCallPushCoordinator()
  private let cellularNetworkInfo = CTTelephonyNetworkInfo()
  private let startupTelemetryJournal = StartupNativeTelemetryJournal()
  private var flutterFirstFrameWatchdog: DispatchWorkItem?
  private var nativeRecoveryTerminalReconciliation: DispatchWorkItem?
  private var deferredPluginRegistry: FlutterPluginRegistry?
  private var retryFlutterEngine: FlutterEngine?
  private var generatedPluginsRegistered = false
  private var flutterFirstFrameConfirmed = false
  private var startupSafeTerminalConfirmed = false
  private var appInForeground = false
  private var nativeRecoveryShown = false
  private var nativeRecoveryDeadlineReached = false
  private var dartStartupAttemptStarted = false
  private var currentDartAttemptId = ""
  private var currentLaunchMode = "unknown"
  private var currentDartAttemptStartedUptime: TimeInterval = 0
  private var firstFrameForegroundRemaining = AppDelegate.flutterFirstFrameDeadline
  private var foregroundStartedUptime: TimeInterval = 0
  private weak var startupRecoveryView: UIView?

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    NativeCrashMarkerStore.install()
    if #available(iOS 14.0, *) {
      NativeHangMetricStore.shared.install()
    }
    NSLog("QWQStartup ios_did_finish_launching")
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)
    configureIncomingCallInfrastructure()
    if let registrar = self.registrar(forPlugin: "QuwoquanNativeMethodChannels") {
      registerMethodChannels(binaryMessenger: registrar.messenger())
    }
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

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    NSLog("QWQStartup ios_implicit_flutter_engine_initialized")
    window?.rootViewController?.view.backgroundColor = StartupTransitionBackground.color
    registerStartupTimingsChannel(
      binaryMessenger: engineBridge.applicationRegistrar.messenger()
    )
    // GeneratedPluginRegistrant 会同步装配 RTC、相机、媒体等重插件。将其延后到 Flutter
    // 首帧确认后，避免 iOS 静态 LaunchScreen 因插件初始化被永久遮挡。
    deferredPluginRegistry = engineBridge.pluginRegistry
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

    let localDevHttpsTrustChannel = FlutterMethodChannel(
      name: "quwoquan/runtime/local_dev_https_trust",
      binaryMessenger: binaryMessenger
    )
    localDevHttpsTrustChannel.setMethodCallHandler { call, result in
      guard call.method == "localEnvDebugRootCertificate" else {
        result(FlutterMethodNotImplemented)
        return
      }
      // 仅由 Debug/Profile 本地 target 构建步骤注入，release 与公网 authority
      // 不会请求或携带本地根证书。
      guard let certificateURL = Bundle.main.url(
        forResource: "local_env_debug_root",
        withExtension: "crt"
      ) else {
        result(
          FlutterError(
            code: "LOCAL_HTTPS_TRUST_CA_UNAVAILABLE",
            message: "Local HTTPS trust root is not bundled",
            details: nil
          )
        )
        return
      }
      do {
        result(FlutterStandardTypedData(bytes: try Data(contentsOf: certificateURL)))
      } catch {
        result(
          FlutterError(
            code: "LOCAL_HTTPS_TRUST_CA_UNREADABLE",
            message: "Local HTTPS trust root cannot be read",
            details: nil
          )
        )
      }
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

    let deferredPluginsChannel = FlutterMethodChannel(
      name: "quwoquan/startup/deferred_plugins",
      binaryMessenger: binaryMessenger
    )
    deferredPluginsChannel.setMethodCallHandler { [weak self] call, result in
      guard call.method == "ensureStartupPostFirstFrame" else {
        result(FlutterMethodNotImplemented)
        return
      }
      // 此调用只从 Dart 已完成 Shell 首帧的 scheduler 发起。统一走首帧
      // 确认入口，避免 channel 路径绕过 `flutterFirstFrameConfirmed` 直接注册。
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
      currentDartAttemptStartedUptime = hotRestart
        ? ProcessInfo.processInfo.systemUptime
        : processStartUptime
      let configurationState = safeStartupEnum(
        event["configurationState"] as? String
      )
      let missingDefineKeys = safeDefineKeyList(event["missingDefineKeys"] as? String)
      NSLog(
        "QWQStartup ios_dart_startup_attempt attemptId=%@ launchMode=%@ hotRestart=%@ configurationState=%@%@",
        currentDartAttemptId,
        currentLaunchMode,
        hotRestart ? "true" : "false",
        configurationState,
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
    super.applicationDidBecomeActive(application)
    if !appInForeground {
      appInForeground = true
      foregroundStartedUptime = ProcessInfo.processInfo.systemUptime
    }
    armFlutterFirstFrameWatchdog()
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
    super.applicationWillResignActive(application)
  }

  override func applicationWillTerminate(_ application: UIApplication) {
    cancelFlutterFirstFrameWatchdog()
    cancelNativeRecoveryTerminalReconciliation()
    super.applicationWillTerminate(application)
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
    // 迟到首帧仍须记账并注册延迟插件；recovery 撤销由 safe_terminal 负责。
    let firstNativeFrame = !flutterFirstFrameConfirmed
    if firstNativeFrame {
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
    if firstNativeFrame {
      registerGeneratedPluginsAfterFirstFrame()
    }
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

  private func registerGeneratedPluginsAfterFirstFrame() {
    guard !generatedPluginsRegistered, let deferredPluginRegistry else { return }
    generatedPluginsRegistered = true
    GeneratedPluginRegistrant.register(with: deferredPluginRegistry)
    NSLog("QWQStartup ios_generated_plugins_registered_after_first_frame")
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
      self.showNativeStartupRecovery(elapsedMs: elapsedMs, recordDeadline: false)
    }
  }

  private func recordNativeStartupDeadline(
    elapsedMs: Int,
    firstFrameMissing: Bool
  ) {
    let outcome = firstFrameMissing ? "native_first_frame_timeout" : "startup_deadline"
    let failureCode = firstFrameMissing ? "OPS.SYSTEM.startup_native_first_frame_timeout" : "OPS.SYSTEM.startup_initialization_failed"
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
      phase: "recovery",
      elapsedMs: elapsedMs,
      outcome: outcome,
      recoverySurface: "native_recovery",
      failureCode: failureCode,
      failureSource: "native_watchdog"
    )
    // native recovery 先可见；120ms 内收到 safe_terminal 视为同帧竞态，
    // 不能与 Flutter terminal 同时落为同一 attempt 的两个终态。
    scheduleNativeRecoveryTerminal(
      elapsedMs: elapsedMs,
      firstFrameMissing: firstFrameMissing
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

  private func showNativeStartupRecovery() {
    let elapsedMs = Int((ProcessInfo.processInfo.systemUptime - processStartUptime) * 1000)
    showNativeStartupRecovery(elapsedMs: elapsedMs, recordDeadline: true)
  }

  private func showNativeStartupRecovery(elapsedMs: Int, recordDeadline: Bool) {
    guard !startupSafeTerminalConfirmed, !nativeRecoveryShown, let window else { return }
    nativeRecoveryShown = true
    if recordDeadline {
      nativeRecoveryDeadlineReached = true
      recordNativeStartupDeadline(
        elapsedMs: elapsedMs,
        firstFrameMissing: !flutterFirstFrameConfirmed
      )
    }

    let recovery = UIView(frame: window.bounds)
    recovery.backgroundColor = StartupTransitionBackground.color
    recovery.autoresizingMask = [.flexibleWidth, .flexibleHeight]

    let title = UILabel()
    title.text = "应用启动遇到问题"
    title.textColor = .white
    title.font = .systemFont(ofSize: 22, weight: .semibold)
    title.textAlignment = .center
    title.translatesAutoresizingMaskIntoConstraints = false

    let message = UILabel()
    message.text = "暂未显示应用界面，请重试或重新打开应用。"
    message.textColor = .white
    message.font = .systemFont(ofSize: 15)
    message.numberOfLines = 0
    message.textAlignment = .center
    message.translatesAutoresizingMaskIntoConstraints = false

    let retry = UIButton(type: .system)
    retry.setTitle("重试", for: .normal)
    retry.setTitleColor(StartupTransitionBackground.color, for: .normal)
    retry.backgroundColor = .white
    retry.layer.cornerRadius = 10
    retry.addTarget(self, action: #selector(retryFlutterStartup), for: .touchUpInside)
    retry.translatesAutoresizingMaskIntoConstraints = false

    recovery.addSubview(title)
    recovery.addSubview(message)
    recovery.addSubview(retry)
    NSLayoutConstraint.activate([
      title.centerXAnchor.constraint(equalTo: recovery.centerXAnchor),
      title.centerYAnchor.constraint(equalTo: recovery.centerYAnchor, constant: -50),
      message.leadingAnchor.constraint(equalTo: recovery.leadingAnchor, constant: 32),
      message.trailingAnchor.constraint(equalTo: recovery.trailingAnchor, constant: -32),
      message.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 16),
      retry.centerXAnchor.constraint(equalTo: recovery.centerXAnchor),
      retry.topAnchor.constraint(equalTo: message.bottomAnchor, constant: 28),
      retry.widthAnchor.constraint(equalToConstant: 108),
      retry.heightAnchor.constraint(equalToConstant: 44),
    ])
    window.addSubview(recovery)
    startupRecoveryView = recovery
  }

  @objc private func retryFlutterStartup() {
    startupRecoveryView?.removeFromSuperview()
    startupRecoveryView = nil
    nativeRecoveryShown = false
    nativeRecoveryDeadlineReached = false
    cancelNativeRecoveryTerminalReconciliation()
    startupTelemetryJournal.beginAttempt()
    startupTelemetryJournal.record(phase: "native_pre_flutter", elapsedMs: 0, outcome: "retry")
    flutterFirstFrameConfirmed = false
    startupSafeTerminalConfirmed = false
    firstFrameForegroundRemaining = Self.flutterFirstFrameDeadline
    foregroundStartedUptime = ProcessInfo.processInfo.systemUptime
    generatedPluginsRegistered = false
    let engine = FlutterEngine(name: "qwq_startup_retry_\(UUID().uuidString)")
    guard engine.run() else {
      showNativeStartupRecovery()
      return
    }
    retryFlutterEngine = engine
    deferredPluginRegistry = engine
    registerStartupTimingsChannel(binaryMessenger: engine.binaryMessenger)
    registerMethodChannels(binaryMessenger: engine.binaryMessenger, includeStartupTimings: false)
    let controller = FlutterViewController(engine: engine, nibName: nil, bundle: nil)
    window?.rootViewController = controller
    window?.makeKeyAndVisible()
    observeNativeFlutterFirstFrame(controller)
    armFlutterFirstFrameWatchdog()
  }

  override func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
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
