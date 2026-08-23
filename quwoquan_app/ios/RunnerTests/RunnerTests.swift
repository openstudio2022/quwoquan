// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-002
import Flutter
import EventKit
import UIKit
import XCTest
@testable import Runner

class RunnerTests: XCTestCase {

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

  private func canonicalDigest(_ character: Character) -> String {
    "sha256:" + String(repeating: String(character), count: 64)
  }

}
