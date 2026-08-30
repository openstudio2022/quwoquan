@import XCTest;
@import patrol;
@import ObjectiveC.runtime;

PATROL_INTEGRATION_TEST_IOS_RUNNER(RunnerUITests)

static NSString *const QWQExternalAUTMarker = @"QWQ_EXTERNAL_AUT ";
static NSString *const QWQExternalAUTSchema =
    @"environment-page-smoke.external-aut-homepage.v1";
static NSString *const QWQHomeSurfaceIdentifier = @"qwq.surface.home";
static NSString *const QWQPatrolHostBundleIdentifier =
    @"com.quwoquan.testhost.patrol";

static BOOL QWQExternalAUTIsActivatableState(XCUIApplicationState state) {
  return state == XCUIApplicationStateRunningBackground
      || state == XCUIApplicationStateRunningForeground;
}

/// XCTest does not expose an XCUIApplication PID in its public header, but the
/// XCTest proxy publishes the observed `processID` value through KVC. Requiring
/// it on both sides of activation lets this black-box test fail closed if the
/// canonical process was replaced.
static NSNumber *QWQExternalAUTProcessID(XCUIApplication *app) {
  @try {
    id value = [app valueForKey:@"processID"];
    if ([value respondsToSelector:@selector(longLongValue)]
        && [value longLongValue] > 0) {
      return @([value longLongValue]);
    }
  } @catch (NSException *exception) {
    NSLog(@"QWQExternalAUT process_id_unavailable %@", exception.name);
  }
  return nil;
}

static NSString *QWQExternalAUTStateName(XCUIApplicationState state) {
  switch (state) {
    case XCUIApplicationStateRunningBackground:
      return @"running_background";
    case XCUIApplicationStateRunningForeground:
      return @"running_foreground";
    default:
      return @"not_activatable";
  }
}

/// Black-box startup/homepage proof for the already-running production AUT.
///
/// This class is intentionally independent from Patrol's generated Dart-test
/// runner. It never installs, terminates, or launches the production App. The
/// canonical launcher must leave the exact AUT running before this test is
/// selected explicitly.
@interface QWQProductionHomepageExternalAUTTests : XCTestCase
@end

@implementation QWQProductionHomepageExternalAUTTests

- (void)setUp {
  [super setUp];
  self.continueAfterFailure = NO;
}

- (void)testReusesCanonicalProductionProcessAndFindsHomeSurface {
  NSDictionary<NSString *, NSString *> *environment =
      NSProcessInfo.processInfo.environment;
  NSString *targetBundleIdentifier =
      [environment[@"QWQ_IOS_TARGET_BUNDLE_ID"]
          stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
  NSString *expectedBundleIdentifier =
      [environment[@"QWQ_IOS_EXPECTED_BUNDLE_ID"]
          stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];

  XCTAssertGreaterThan(targetBundleIdentifier.length, 0);
  XCTAssertEqualObjects(
      targetBundleIdentifier,
      expectedBundleIdentifier,
      @"production bundle selector must equal the artifact identity"
  );
  XCTAssertNotEqualObjects(targetBundleIdentifier, QWQPatrolHostBundleIdentifier);

  NSString *driverBundleIdentifier = NSBundle.mainBundle.bundleIdentifier ?: @"";
  XCTAssertGreaterThan(driverBundleIdentifier.length, 0);
  XCTAssertNotEqualObjects(targetBundleIdentifier, driverBundleIdentifier);

  XCUIApplication *app =
      [[XCUIApplication alloc] initWithBundleIdentifier:targetBundleIdentifier];
  XCUIApplicationState stateBefore = app.state;
  XCTAssertTrue(
      QWQExternalAUTIsActivatableState(stateBefore),
      @"canonical production AUT must already be running before XCTest activation"
  );
  NSNumber *pidBefore = QWQExternalAUTProcessID(app);
  XCTAssertNotNil(pidBefore, @"XCTest must expose the already-running AUT PID");

  // `activate` can launch a stopped app, so the running-state and PID checks
  // above are mandatory preconditions. This call only brings that process to
  // the foreground; PID equality below proves it was not replaced.
  [app activate];
  XCTAssertTrue(
      [app waitForState:XCUIApplicationStateRunningForeground timeout:10.0]
  );
  NSNumber *pidAfter = QWQExternalAUTProcessID(app);
  XCTAssertNotNil(pidAfter);
  XCTAssertEqualObjects(
      pidBefore,
      pidAfter,
      @"activating the canonical AUT must not replace its process"
  );

  XCUIElement *homeSurface = [[app descendantsMatchingType:XCUIElementTypeAny]
      elementMatchingType:XCUIElementTypeAny
      identifier:QWQHomeSurfaceIdentifier];
  XCTAssertTrue(
      [homeSurface waitForExistenceWithTimeout:15.0],
      @"foreground production AUT must expose the canonical home accessibility identity"
  );
  XCTAssertEqualObjects(homeSurface.identifier, QWQHomeSurfaceIdentifier);
  XCTAssertFalse(CGRectIsEmpty(homeSurface.frame));
  XCUIElement *visibleWindow = app.windows.firstMatch;
  XCTAssertTrue(
      [visibleWindow waitForExistenceWithTimeout:2.0],
      @"production AUT must expose its foreground visible window"
  );
  CGRect visibleIntersection = CGRectIntersection(
      homeSurface.frame,
      visibleWindow.frame
  );
  XCTAssertFalse(
      CGRectIsNull(visibleIntersection) || CGRectIsEmpty(visibleIntersection),
      @"canonical home surface must intersect the production App visible window"
  );

  XCTAssertEqual(
      app.state,
      XCUIApplicationStateRunningForeground,
      @"production AUT must remain foreground immediately before evidence emission"
  );
  NSNumber *pidAtMarker = QWQExternalAUTProcessID(app);
  XCTAssertNotNil(pidAtMarker);
  XCTAssertEqualObjects(
      pidBefore,
      pidAtMarker,
      @"production AUT PID must remain canonical through evidence emission"
  );

  NSDictionary<NSString *, id> *evidence = @{
    @"schema": QWQExternalAUTSchema,
    @"platform": @"ios",
    @"driverApplicationId": driverBundleIdentifier,
    @"testHostApplicationId": QWQPatrolHostBundleIdentifier,
    @"productionApplicationId": targetBundleIdentifier,
    @"processIdBefore": pidBefore,
    @"processIdAfter": pidAtMarker,
    @"stateBefore": QWQExternalAUTStateName(stateBefore),
    @"stateAfter": @"running_foreground",
    @"activationMode": @"activate_existing_process",
    @"launchPerformed": @NO,
    @"homepageAccessibilityIdentifier": QWQHomeSurfaceIdentifier,
    @"homepageVisible": @YES,
    @"homepageFrameIntersectsVisibleWindow": @YES,
  };
  NSError *jsonError = nil;
  NSData *jsonData = [NSJSONSerialization dataWithJSONObject:evidence
                                                    options:0
                                                      error:&jsonError];
  XCTAssertNil(jsonError);
  XCTAssertNotNil(jsonData);
  NSString *json = [[NSString alloc] initWithData:jsonData
                                         encoding:NSUTF8StringEncoding];
  XCTAssertNotNil(json);
  NSLog(@"%@%@", QWQExternalAUTMarker, json);
}

@end

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
