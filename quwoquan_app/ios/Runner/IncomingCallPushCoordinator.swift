import Foundation
import PushKit
import Security
import flutter_callkit_incoming

final class IncomingCallPushCoordinator {
  private enum StoreKey {
    static let voipToken = "qwq.rtc.apns_voip.active_token"
    static let endpointMutations = "qwq.rtc.push_endpoint.mutations"
    static let pendingCalls = "qwq.rtc.incoming.pending_calls"
    static let pendingActions = "qwq.rtc.incoming.pending_actions"
    static let seenDeliveries = "qwq.rtc.incoming.seen_deliveries"
  }

  private static let maxPending = 32
  private static let maxSeen = 128

  private let defaults: UserDefaults
  private let secretStore: IncomingCallKeychainStore
  private(set) var pushRegistry: PKPushRegistry?
  private var flutterReady = false

  init(
    defaults: UserDefaults = .standard,
    secretStore: IncomingCallKeychainStore = IncomingCallKeychainStore()
  ) {
    self.defaults = defaults
    self.secretStore = secretStore
    migrateLegacySecrets()
  }

  private func migrateLegacySecrets() {
    if let token = defaults.string(forKey: StoreKey.voipToken),
       !token.isEmpty,
       secretStore.set(token, forKey: StoreKey.voipToken)
    {
      defaults.removeObject(forKey: StoreKey.voipToken)
    }
    if let mutations = defaults.array(forKey: StoreKey.endpointMutations),
       JSONSerialization.isValidJSONObject(mutations),
       let encoded = try? JSONSerialization.data(withJSONObject: mutations),
       secretStore.set(encoded, forKey: StoreKey.endpointMutations)
    {
      defaults.removeObject(forKey: StoreKey.endpointMutations)
    }
  }

  var backgroundPushConfigured: Bool {
    pushRegistry != nil && SwiftFlutterCallkitIncomingPlugin.sharedInstance != nil
  }

  func startPushKit(delegate: PKPushRegistryDelegate) {
    guard pushRegistry == nil,
          SwiftFlutterCallkitIncomingPlugin.sharedInstance != nil
    else {
      return
    }
    let registry = PKPushRegistry(queue: .main)
    registry.delegate = delegate
    pushRegistry = registry
    registry.desiredPushTypes = [.voIP]
  }

  func updateVoipToken(_ tokenData: Foundation.Data) {
    let token = tokenData.map { String(format: "%02x", $0) }.joined()
    guard !token.isEmpty else { return }
    let previous = secretStore.string(forKey: StoreKey.voipToken) ?? ""
    guard secretStore.set(token, forKey: StoreKey.voipToken) else {
      return
    }
    if previous != token {
      appendEndpointMutation(action: "upsert", token: token)
    }
    SwiftFlutterCallkitIncomingPlugin.sharedInstance?
      .setDevicePushTokenVoIP(token)
  }

  func invalidateVoipToken() {
    let previous = secretStore.string(forKey: StoreKey.voipToken) ?? ""
    if !previous.isEmpty {
      appendEndpointMutation(action: "remove", token: previous)
    }
    secretStore.remove(StoreKey.voipToken)
    SwiftFlutterCallkitIncomingPlugin.sharedInstance?
      .setDevicePushTokenVoIP("")
  }

  func reportIncomingPush(
    payload: PKPushPayload,
    type: PKPushType,
    completion: @escaping () -> Void
  ) {
    let completionOnce = CompletionOnce(completion)
    guard type == .voIP,
          let envelope = IncomingNativeEnvelope(payload.dictionaryPayload),
          let plugin = SwiftFlutterCallkitIncomingPlugin.sharedInstance
    else {
      completionOnce.call()
      return
    }

    let now = Date()
    guard envelope.expiresAt > now,
          envelope.expiresAt <= now.addingTimeInterval(90),
          envelope.occurredAt <= now.addingTimeInterval(300)
    else {
      completionOnce.call()
      return
    }
    let data = makeCallKitData(envelope)
    purgeSeen(now: now)
    if envelope.action == "cancel" {
      rememberSeen(envelope)
      removePendingCall(envelope)
      plugin.endCall(data)
      completionOnce.call()
      return
    }
    if isDuplicate(envelope) {
      if envelope.expiresAt <= now {
        plugin.endCall(data)
      }
      completionOnce.call()
      return
    }

    rememberSeen(envelope)
    appendPendingCall(envelope)
    DispatchQueue.main.asyncAfter(deadline: .now() + 4.5) {
      // PushKit 要求及时调用 completion；插件异常不得让系统终止后续 VoIP push。
      completionOnce.call()
    }
    plugin.showCallkitIncoming(data, fromPushKit: true) {
      if envelope.expiresAt <= Date() {
        plugin.endCall(data)
      }
      // PushKit completion 必须在 CallKit report completion 之后。
      completionOnce.call()
    }
  }

  func persistAction(callId: String, action: String) {
    // Flutter event channel 已订阅时由插件直接投递；仅 engine/监听器未就绪时落盘。
    guard !flutterReady else { return }
    guard UUID(uuidString: callId) != nil else { return }
    var actions = defaults.array(forKey: StoreKey.pendingActions)
      as? [[String: String]] ?? []
    actions.append([
      "callId": callId.lowercased(),
      "action": action,
      "occurredAt": ISO8601DateFormatter().string(from: Date()),
    ])
    trim(&actions, limit: Self.maxPending)
    defaults.set(actions, forKey: StoreKey.pendingActions)
  }

  func setFlutterReady(_ ready: Bool) {
    flutterReady = ready
  }

  func consumePendingActions() -> [[String: String]] {
    let actions = defaults.array(forKey: StoreKey.pendingActions)
      as? [[String: String]] ?? []
    defaults.removeObject(forKey: StoreKey.pendingActions)
    return actions
  }

  func consumePendingCalls() -> [[String: String]] {
    let now = Date()
    let calls = (defaults.array(forKey: StoreKey.pendingCalls)
      as? [[String: String]] ?? []).filter {
        guard let value = $0["expiresAt"],
              let expiresAt = Self.parseDate(value)
        else {
          return false
        }
        return expiresAt > now
      }
    defaults.removeObject(forKey: StoreKey.pendingCalls)
    return calls
  }

  func endpointMutations() -> [[String: String]] {
    var mutations = storedEndpointMutations()
    let activeToken = secretStore.string(forKey: StoreKey.voipToken) ?? ""
    let alreadyQueued = mutations.contains {
      $0["endpointKind"] == "apns_voip"
        && $0["token"] == activeToken
    }
    if !activeToken.isEmpty && !alreadyQueued {
      let mutation = makeEndpointMutation(
        action: "upsert",
        token: activeToken
      )
      mutations.append(mutation)
      trim(&mutations, limit: Self.maxPending)
      storeEndpointMutations(mutations)
    }
    return mutations
  }

  func acknowledgeEndpointMutation(_ mutationId: String) {
    var mutations = endpointMutations()
    mutations.removeAll { $0["mutationId"] == mutationId }
    storeEndpointMutations(mutations)
  }

  func queueActiveEndpointRemoval() {
    let token = secretStore.string(forKey: StoreKey.voipToken) ?? ""
    if !token.isEmpty {
      appendEndpointMutation(action: "remove", token: token)
    }
  }

  func purgeForTerminalAccountClosure() -> Bool {
    secretStore.remove(StoreKey.voipToken)
    secretStore.remove(StoreKey.endpointMutations)
    defaults.removeObject(forKey: StoreKey.pendingCalls)
    defaults.removeObject(forKey: StoreKey.pendingActions)
    defaults.removeObject(forKey: StoreKey.seenDeliveries)
    return secretStore.string(forKey: StoreKey.voipToken) == nil
      && secretStore.data(forKey: StoreKey.endpointMutations) == nil
      && defaults.object(forKey: StoreKey.pendingCalls) == nil
      && defaults.object(forKey: StoreKey.pendingActions) == nil
      && defaults.object(forKey: StoreKey.seenDeliveries) == nil
  }

  private func makeCallKitData(
    _ envelope: IncomingNativeEnvelope
  ) -> flutter_callkit_incoming.Data {
    let data = flutter_callkit_incoming.Data(
      id: envelope.callId,
      nameCaller: envelope.callerName,
      handle: envelope.callerName,
      type: envelope.callType == "video" ? 1 : 0
    )
    data.appName =
      Bundle.main.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String
      ?? Bundle.main.object(forInfoDictionaryKey: "CFBundleName") as? String
      ?? ""
    data.duration = max(
      1_000,
      min(30_000, Int(envelope.expiresAt.timeIntervalSinceNow * 1_000))
    )
    data.extra = envelope.dictionary as NSDictionary
    data.handleType = "generic"
    data.supportsVideo = true
    data.maximumCallGroups = 1
    data.maximumCallsPerCallGroup = 1
    data.supportsDTMF = false
    data.supportsHolding = false
    data.supportsGrouping = false
    data.supportsUngrouping = false
    data.isShowMissedCallNotification = false
    return data
  }

  private func appendPendingCall(_ envelope: IncomingNativeEnvelope) {
    var calls = defaults.array(forKey: StoreKey.pendingCalls)
      as? [[String: String]] ?? []
    calls.removeAll {
      $0["deliveryKey"] == envelope.deliveryKey
        || $0["callId"] == envelope.callId
    }
    calls.append(envelope.dictionary)
    trim(&calls, limit: Self.maxPending)
    defaults.set(calls, forKey: StoreKey.pendingCalls)
  }

  private func removePendingCall(_ envelope: IncomingNativeEnvelope) {
    var calls = defaults.array(forKey: StoreKey.pendingCalls)
      as? [[String: String]] ?? []
    calls.removeAll {
      $0["deliveryKey"] == envelope.deliveryKey
        || $0["callId"] == envelope.callId
    }
    defaults.set(calls, forKey: StoreKey.pendingCalls)
  }

  private func appendEndpointMutation(action: String, token: String) {
    var mutations = storedEndpointMutations()
    mutations.removeAll {
      $0["action"] == action
        && $0["endpointKind"] == "apns_voip"
        && $0["token"] == token
    }
    mutations.append(makeEndpointMutation(action: action, token: token))
    trim(&mutations, limit: Self.maxPending)
    storeEndpointMutations(mutations)
  }

  private func storedEndpointMutations() -> [[String: String]] {
    guard let encoded = secretStore.data(
      forKey: StoreKey.endpointMutations
    ),
          let decoded = try? JSONSerialization.jsonObject(with: encoded),
          let mutations = decoded as? [[String: String]]
    else {
      return []
    }
    return mutations
  }

  private func storeEndpointMutations(_ mutations: [[String: String]]) {
    guard !mutations.isEmpty else {
      secretStore.remove(StoreKey.endpointMutations)
      return
    }
    guard let encoded = try? JSONSerialization.data(withJSONObject: mutations)
    else {
      return
    }
    _ = secretStore.set(encoded, forKey: StoreKey.endpointMutations)
  }

  private func makeEndpointMutation(
    action: String,
    token: String
  ) -> [String: String] {
    [
      "mutationId": UUID().uuidString.lowercased(),
      "action": action,
      "endpointKind": "apns_voip",
      "token": token,
      "occurredAt": ISO8601DateFormatter().string(from: Date()),
    ]
  }

  private func isDuplicate(_ envelope: IncomingNativeEnvelope) -> Bool {
    let seen = defaults.array(forKey: StoreKey.seenDeliveries)
      as? [[String: String]] ?? []
    return seen.contains {
      $0["deliveryKey"] == envelope.deliveryKey
        || $0["callId"] == envelope.callId
    }
  }

  private func rememberSeen(_ envelope: IncomingNativeEnvelope) {
    var seen = defaults.array(forKey: StoreKey.seenDeliveries)
      as? [[String: String]] ?? []
    seen.removeAll {
      $0["deliveryKey"] == envelope.deliveryKey
        || $0["callId"] == envelope.callId
    }
    seen.append([
      "action": envelope.action,
      "deliveryKey": envelope.deliveryKey,
      "callId": envelope.callId,
      "expiresAt": Self.formatDate(envelope.expiresAt),
      "occurredAt": Self.formatDate(envelope.occurredAt),
    ])
    trim(&seen, limit: Self.maxSeen)
    defaults.set(seen, forKey: StoreKey.seenDeliveries)
  }

  private func purgeSeen(now: Date) {
    var seen = defaults.array(forKey: StoreKey.seenDeliveries)
      as? [[String: String]] ?? []
    seen.removeAll {
      guard let value = $0["expiresAt"],
            let expiresAt = Self.parseDate(value)
      else {
        return true
      }
      return expiresAt <= now
    }
    defaults.set(seen, forKey: StoreKey.seenDeliveries)
  }

  private func trim(
    _ entries: inout [[String: String]],
    limit: Int
  ) {
    if entries.count > limit {
      entries.removeFirst(entries.count - limit)
    }
  }

  fileprivate static func parseDate(_ value: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return fractional.date(from: value)
      ?? ISO8601DateFormatter().date(from: value)
  }

  fileprivate static func formatDate(_ value: Date) -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return formatter.string(from: value)
  }
}

private struct IncomingNativeEnvelope {
  let action: String
  let callId: String
  let deliveryKey: String
  let targetPersonaId: String
  let callType: String
  let callerName: String
  let sourceLabel: String
  let trustRelation: String
  let expiresAt: Date
  let occurredAt: Date
  let callerPersonaId: String?

  init?(_ payload: [AnyHashable: Any]) {
    guard let action = Self.requiredString(payload["action"], max: 16),
          action == "ring" || action == "cancel",
          let callId = Self.requiredString(payload["callId"], max: 36),
          UUID(uuidString: callId) != nil,
          let deliveryKey = Self.requiredString(payload["deliveryKey"], max: 256),
          let targetPersonaId = Self.requiredString(payload["targetPersonaId"], max: 128),
          let callType = Self.requiredString(payload["callType"], max: 16),
          callType == "audio" || callType == "video",
          let callerName = Self.requiredString(payload["callerName"], max: 160),
          let sourceLabel = Self.requiredString(payload["sourceLabel"], max: 160),
          let trustRelation = Self.requiredString(payload["trustRelation"], max: 64),
          trustRelation == "known" || trustRelation == "possibly_unknown",
          let expiresAtValue = Self.requiredString(payload["expiresAt"], max: 64),
          let expiresAt = IncomingCallPushCoordinator.parseDate(expiresAtValue),
          let occurredAtValue = Self.requiredString(payload["occurredAt"], max: 64),
          let occurredAt = IncomingCallPushCoordinator.parseDate(occurredAtValue),
          occurredAt <= expiresAt
    else {
      return nil
    }
    self.action = action
    self.callId = callId.lowercased()
    self.deliveryKey = deliveryKey
    self.targetPersonaId = targetPersonaId
    self.callType = callType
    self.callerName = callerName
    self.sourceLabel = sourceLabel
    self.trustRelation = trustRelation
    self.expiresAt = expiresAt
    self.occurredAt = occurredAt
    self.callerPersonaId = Self.optionalString(
      payload["callerPersonaId"],
      max: 128
    )
  }

  var dictionary: [String: String] {
    var value = [
      "action": action,
      "callId": callId,
      "deliveryKey": deliveryKey,
      "targetPersonaId": targetPersonaId,
      "callType": callType,
      "callerName": callerName,
      "sourceLabel": sourceLabel,
      "trustRelation": trustRelation,
      "expiresAt": IncomingCallPushCoordinator.formatDate(expiresAt),
      "occurredAt": IncomingCallPushCoordinator.formatDate(occurredAt),
    ]
    if let callerPersonaId {
      value["callerPersonaId"] = callerPersonaId
    }
    return value
  }

  private static func requiredString(
    _ raw: Any?,
    max: Int
  ) -> String? {
    guard let value = raw as? String else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty, normalized.count <= max else { return nil }
    return normalized
  }

  private static func optionalString(
    _ raw: Any?,
    max: Int
  ) -> String? {
    guard let value = raw as? String else { return nil }
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty, normalized.count <= max else { return nil }
    return normalized
  }
}

private final class CompletionOnce {
  private let lock = NSLock()
  private var completion: (() -> Void)?

  init(_ completion: @escaping () -> Void) {
    self.completion = completion
  }

  func call() {
    lock.lock()
    let callback = completion
    completion = nil
    lock.unlock()
    callback?()
  }
}

final class IncomingCallKeychainStore {
  private let service: String

  init(
    service: String =
      "\(Bundle.main.bundleIdentifier ?? "com.quwoquan.app").rtc.push"
  ) {
    self.service = service
  }

  func string(forKey key: String) -> String? {
    guard let value = data(forKey: key) else { return nil }
    return String(data: value, encoding: .utf8)
  }

  func data(forKey key: String) -> Foundation.Data? {
    var query = baseQuery(forKey: key)
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess else { return nil }
    return result as? Foundation.Data
  }

  @discardableResult
  func set(_ value: String, forKey key: String) -> Bool {
    guard let encoded = value.data(using: .utf8) else { return false }
    return set(encoded, forKey: key)
  }

  @discardableResult
  func set(_ value: Foundation.Data, forKey key: String) -> Bool {
    let query = baseQuery(forKey: key)
    let attributes = [kSecValueData as String: value]
    let updateStatus = SecItemUpdate(
      query as CFDictionary,
      attributes as CFDictionary
    )
    if updateStatus == errSecSuccess {
      return true
    }
    guard updateStatus == errSecItemNotFound else { return false }
    var insertion = query
    insertion[kSecValueData as String] = value
    insertion[kSecAttrAccessible as String] =
      kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
    return SecItemAdd(insertion as CFDictionary, nil) == errSecSuccess
  }

  func remove(_ key: String) {
    SecItemDelete(baseQuery(forKey: key) as CFDictionary)
  }

  private func baseQuery(forKey key: String) -> [String: Any] {
    [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrService as String: service,
      kSecAttrAccount as String: key,
    ]
  }
}
