import Flutter
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

}
