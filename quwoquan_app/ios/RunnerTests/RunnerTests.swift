import Flutter
import EventKit
import UIKit
import XCTest
@testable import Runner

class RunnerTests: XCTestCase {

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

  func testCalendarReminderRequestValidatesAndClampsNativeBounds() throws {
    let request = try XCTUnwrap(CalendarReminderRequest([
      "idempotencyKey": "arn_1:tool_1",
      "title": "  提交周报  ",
      "startsAtEpochMs": NSNumber(value: 1_800_000_000_000),
      "durationMinutes": NSNumber(value: -20),
      "reminderMinutes": NSNumber(value: 99_999),
      "notes": String(repeating: "长", count: 2_100),
    ]))

    XCTAssertEqual(request.idempotencyKey, "arn_1:tool_1")
    XCTAssertEqual(request.title, "提交周报")
    XCTAssertEqual(request.durationMinutes, 1)
    XCTAssertEqual(request.reminderMinutes, 10_080)
    XCTAssertEqual(request.notes.count, 2_000)
  }

  func testCalendarReminderRequestRejectsMissingIdempotencyKey() {
    XCTAssertNil(CalendarReminderRequest([
      "idempotencyKey": "",
      "title": "提交周报",
      "startsAtEpochMs": NSNumber(value: 1_800_000_000_000),
    ]))
  }

  func testCalendarReminderCreationIsIdempotentAndReadable() throws {
    let eventStore = EKEventStore()
    let plugin = AssistantDeviceActionPlugin(eventStore: eventStore)
    let idempotencyKey = "native-test-\(UUID().uuidString.lowercased())"
    let preferenceKey = "qwq.assistant.calendar.\(idempotencyKey)"
    defer {
      UserDefaults.standard.removeObject(forKey: preferenceKey)
    }
    let arguments: [String: Any] = [
      "idempotencyKey": idempotencyKey,
      "title": "小趣原生合同测试",
      "startsAtEpochMs": NSNumber(
        value: Int64(Date().addingTimeInterval(3_600).timeIntervalSince1970 * 1_000)
      ),
      "durationMinutes": NSNumber(value: 15),
      "reminderMinutes": NSNumber(value: 5),
      "notes": "确认后创建且重复调用不重复写入",
    ]

    let first = invokeCalendarReminder(
      plugin: plugin,
      arguments: arguments,
      label: "first calendar write"
    )
    XCTAssertEqual(first["status"] as? String, "created")
    let identifier = try XCTUnwrap(first["deviceObjectId"] as? String)
    let event = try XCTUnwrap(eventStore.event(withIdentifier: identifier))
    defer {
      try? eventStore.remove(event, span: .thisEvent, commit: true)
    }
    XCTAssertFalse(event.url?.absoluteString.contains(idempotencyKey) ?? true)
    UserDefaults.standard.removeObject(forKey: preferenceKey)

    let replay = invokeCalendarReminder(
      plugin: plugin,
      arguments: arguments,
      label: "idempotent calendar restart recovery"
    )
    XCTAssertEqual(replay["status"] as? String, "created")
    XCTAssertEqual(replay["deviceObjectId"] as? String, identifier)
    XCTAssertNotNil(eventStore.event(withIdentifier: identifier))
  }

  private func invokeCalendarReminder(
    plugin: AssistantDeviceActionPlugin,
    arguments: [String: Any],
    label: String
  ) -> [String: Any] {
    let completed = expectation(description: label)
    var response: [String: Any] = [:]
    plugin.handle(
      call: FlutterMethodCall(
        methodName: "createCalendarReminder",
        arguments: arguments
      )
    ) { value in
      response = value as? [String: Any] ?? [:]
      completed.fulfill()
    }
    wait(for: [completed], timeout: 5)
    return response
  }

}
