import AVFoundation
import CallKit
import Flutter
import PushKit
import flutter_callkit_incoming

private let incomingCallBootstrapPluginKey =
  "QuwoquanIncomingCallBootstrapPlugin"

extension AppDelegate: PKPushRegistryDelegate, CallkitIncomingAppDelegate {
  func configureIncomingCallInfrastructure() {
    guard let registrar = registrar(
      forPlugin: incomingCallBootstrapPluginKey
    ) else {
      return
    }
    // CallKit 必须早于 PushKit。bootstrap 使用独立 registry key，官方插件 key 只交给
    // GeneratedPluginRegistrant；插件再按 messenger 幂等，避免首帧后二次占用同一 key 崩溃。
    SwiftFlutterCallkitIncomingPlugin.register(with: registrar)
    incomingCallPushCoordinator.startPushKit(delegate: self)
    registerIncomingCallChannel(binaryMessenger: registrar.messenger())
  }

  private func registerIncomingCallChannel(
    binaryMessenger: FlutterBinaryMessenger
  ) {
    let channel = FlutterMethodChannel(
      name: "quwoquan/rtc/incoming_call",
      binaryMessenger: binaryMessenger
    )
    channel.setMethodCallHandler { [weak self] call, result in
      guard let self else {
        result(
          FlutterError(
            code: "RTC.NATIVE.UNAVAILABLE",
            message: nil,
            details: nil
          )
        )
        return
      }
      switch call.method {
      case "readPendingIncomingCalls":
        result(incomingCallPushCoordinator.consumePendingCalls())
      case "consumePendingIncomingCallActions":
        result(incomingCallPushCoordinator.consumePendingActions())
      case "setIncomingCallFlutterReady":
        guard let arguments = call.arguments as? [String: Any],
              let ready = arguments["ready"] as? Bool
        else {
          result(
            FlutterError(
              code: "RTC.NATIVE.INVALID_ARGUMENT",
              message: nil,
              details: nil
            )
          )
          return
        }
        incomingCallPushCoordinator.setFlutterReady(ready)
        result(nil)
      case "readIncomingCallCapability":
        result([
          "backgroundPushConfigured":
            incomingCallPushCoordinator.backgroundPushConfigured,
        ])
      case "readPushEndpointMutations":
        result(incomingCallPushCoordinator.endpointMutations())
      case "ackPushEndpointMutation":
        guard let arguments = call.arguments as? [String: Any],
              let mutationId = arguments["mutationId"] as? String
        else {
          result(
            FlutterError(
              code: "RTC.NATIVE.INVALID_ARGUMENT",
              message: nil,
              details: nil
            )
          )
          return
        }
        incomingCallPushCoordinator
          .acknowledgeEndpointMutation(mutationId)
        result(nil)
      case "queueActivePushEndpointRemovals":
        incomingCallPushCoordinator.queueActiveEndpointRemoval()
        result(nil)
      default:
        result(FlutterMethodNotImplemented)
      }
    }
  }

  func pushRegistry(
    _ registry: PKPushRegistry,
    didUpdate pushCredentials: PKPushCredentials,
    for type: PKPushType
  ) {
    guard type == .voIP else { return }
    incomingCallPushCoordinator.updateVoipToken(pushCredentials.token)
  }

  func pushRegistry(
    _ registry: PKPushRegistry,
    didInvalidatePushTokenFor type: PKPushType
  ) {
    guard type == .voIP else { return }
    incomingCallPushCoordinator.invalidateVoipToken()
  }

  func pushRegistry(
    _ registry: PKPushRegistry,
    didReceiveIncomingPushWith payload: PKPushPayload,
    for type: PKPushType,
    completion: @escaping () -> Void
  ) {
    incomingCallPushCoordinator.reportIncomingPush(
      payload: payload,
      type: type,
      completion: completion
    )
  }

  func onAccept(_ call: Call, _ action: CXAnswerCallAction) {
    incomingCallPushCoordinator.persistAction(
      callId: call.uuid.uuidString,
      action: "accept"
    )
    action.fulfill()
  }

  func onDecline(_ call: Call, _ action: CXEndCallAction) {
    incomingCallPushCoordinator.persistAction(
      callId: call.uuid.uuidString,
      action: "decline"
    )
    action.fulfill()
  }

  func onEnd(_ call: Call, _ action: CXEndCallAction) {
    incomingCallPushCoordinator.persistAction(
      callId: call.uuid.uuidString,
      action: "end"
    )
    action.fulfill()
  }

  func onTimeOut(_ call: Call) {
    incomingCallPushCoordinator.persistAction(
      callId: call.uuid.uuidString,
      action: "timeout"
    )
  }

  func didActivateAudioSession(_ audioSession: AVAudioSession) {}

  func didDeactivateAudioSession(_ audioSession: AVAudioSession) {}

  func providerDidReset() {}
}
