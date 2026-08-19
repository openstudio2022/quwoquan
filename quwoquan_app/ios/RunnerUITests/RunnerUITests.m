@import XCTest;
@import patrol;
@import ObjectiveC.runtime;

PATROL_INTEGRATION_TEST_IOS_RUNNER(RunnerUITests)

@interface QWQNativeStartupRecoveryWebUITests : XCTestCase
@end

@implementation QWQNativeStartupRecoveryWebUITests

- (void)setUp {
  [super setUp];
  self.continueAfterFailure = NO;
}

- (void)testRecoveryWebCTAOpensSafariAndReturnsToSameProcess {
  XCUIApplication *app = [[XCUIApplication alloc] init];
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
