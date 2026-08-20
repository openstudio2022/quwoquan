@import XCTest;
@import patrol;

PATROL_INTEGRATION_TEST_IOS_RUNNER(RunnerUITests)

/// 原生启动恢复页的「使用网页版」CTA 是被测生产 App 的黑盒 UAT。
///
/// 生产 iOS 工程不持有任何 test target，因此 runner 归本 test host；被测对象由
/// QWQ_IOS_TARGET_BUNDLE_ID 指定为当前环境已安装的生产 App，不是 host 自身。
@interface QWQNativeStartupRecoveryWebUITests : XCTestCase
@end

@implementation QWQNativeStartupRecoveryWebUITests

- (void)setUp {
  [super setUp];
  self.continueAfterFailure = NO;
}

- (void)testRecoveryWebCTAOpensSafariAndReturnsToSameProcess {
  NSString *bundleIdentifier =
      NSProcessInfo.processInfo.environment[@"QWQ_IOS_TARGET_BUNDLE_ID"];
  XCTAssertGreaterThan(
      bundleIdentifier.length,
      0,
      @"QWQ_IOS_TARGET_BUNDLE_ID must name the production App under test"
  );

  XCUIApplication *app =
      [[XCUIApplication alloc] initWithBundleIdentifier:bundleIdentifier];
  app.launchArguments = @[@"--qwq-test-confirmed-startup-fatal"];
  [app launch];

  XCUIElement *secondary = app.buttons[@"qwq.native.startup.recovery.web"];
  XCUIElement *primary = app.buttons[@"qwq.native.startup.recovery.primary"];
  XCUIElement *cta = nil;
  if ([secondary waitForExistenceWithTimeout:2.0] && secondary.hittable) {
    cta = secondary;
  } else {
    XCTAssertTrue([primary waitForExistenceWithTimeout:5.0]);
    XCTAssertTrue(primary.hittable);
    XCTAssertEqualObjects(primary.label, @"使用网页版");
    cta = primary;
  }

  [cta tap];

  XCUIApplication *safari = [[XCUIApplication alloc]
      initWithBundleIdentifier:@"com.apple.mobilesafari"];
  XCTAssertTrue(
      [safari waitForState:XCUIApplicationStateRunningForeground timeout:10.0]
  );
  NSLog(@"QWQNativeStartupUITest recovery_web_cta_safari_foreground");

  [app activate];
  XCTAssertTrue(
      [app waitForState:XCUIApplicationStateRunningForeground timeout:10.0]
  );
  XCTAssertTrue(
      [app.buttons[@"qwq.native.startup.recovery.primary"]
          waitForExistenceWithTimeout:5.0]
      || [app.buttons[@"qwq.native.startup.recovery.web"]
          waitForExistenceWithTimeout:1.0]
  );
  NSLog(@"QWQNativeStartupUITest recovery_web_cta_returned_app_foreground");
}

@end
