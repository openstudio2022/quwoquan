@import XCTest;
@import patrol;
@import ObjectiveC.runtime;
#import <CommonCrypto/CommonDigest.h>

static NSString *QWQOfflineScreenshotDigest(NSData *data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString *hex = [NSMutableString stringWithString:@"sha256:"];
  for (NSUInteger index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) {
    [hex appendFormat:@"%02x", digest[index]];
  }
  return hex;
}

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

- (NSPredicate *)offlinePredicate:(NSString *)selector {
  if ([selector hasPrefix:@"text-prefix:"]) {
    NSString *prefix = [selector substringFromIndex:@"text-prefix:".length];
    return [NSPredicate predicateWithFormat:@"label BEGINSWITH %@", prefix];
  }
  return [NSPredicate predicateWithFormat:@"identifier == %@ OR label == %@", selector, selector];
}

- (XCUIElement *)offlineElement:(NSString *)selector app:(XCUIApplication *)app {
  XCUIElement *element = [[app descendantsMatchingType:XCUIElementTypeAny]
      matchingPredicate:[self offlinePredicate:selector]].firstMatch;
  XCTAssertTrue([element waitForExistenceWithTimeout:15.0], @"实际页面缺少 %@", selector);
  return element;
}

- (NSArray<NSNumber *> *)offlinePlaybackTimes:(NSString *)value {
  NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:
      @"(\\d+):(\\d{2})\\s*/\\s*(\\d+):(\\d{2})" options:0 error:nil];
  NSTextCheckingResult *match = [regex firstMatchInString:value options:0 range:NSMakeRange(0, value.length)];
  XCTAssertNotNil(match, @"实际进度必须含当前时间和总时长");
  NSInteger current = [[value substringWithRange:[match rangeAtIndex:1]] integerValue] * 60
      + [[value substringWithRange:[match rangeAtIndex:2]] integerValue];
  NSInteger duration = [[value substringWithRange:[match rangeAtIndex:3]] integerValue] * 60
      + [[value substringWithRange:[match rangeAtIndex:4]] integerValue];
  return @[@(current), @(duration)];
}

- (void)testExecutesOfflinePageCaseInCanonicalProductionProcess {
  NSDictionary *environment = NSProcessInfo.processInfo.environment;
  NSString *target = environment[@"QWQ_IOS_TARGET_BUNDLE_ID"];
  XCTAssertGreaterThan(target.length, 0);
  XCTAssertEqualObjects(target, environment[@"QWQ_IOS_EXPECTED_BUNDLE_ID"]);
  XCTAssertNotEqualObjects(target, QWQPatrolHostBundleIdentifier);
  XCTAssertNotEqualObjects(target, NSBundle.mainBundle.bundleIdentifier);
  NSData *encoded = [[NSData alloc] initWithBase64EncodedString:environment[@"QWQ_OFFLINE_PAGE_PLAN"] options:0];
  NSDictionary *plan = [NSJSONSerialization JSONObjectWithData:encoded options:0 error:nil];
  XCTAssertEqualObjects(plan[@"schema"], @"quwoquan_ops.offline_page_case.v1");
  XCTAssertEqualObjects(plan[@"applicationId"], target);
  XCTAssertEqualObjects(plan[@"platform"], @"ios");
  NSArray *steps = plan[@"steps"];
  XCTAssertTrue([steps isKindOfClass:NSArray.class]);
  XCTAssertTrue(steps.count > 0 && steps.count <= 40);
  NSSet *operations = [NSSet setWithArray:@[@"visible", @"tap", @"scroll", @"seek", @"playback", @"back", @"reveal"]];
  for (NSDictionary *step in steps) {
    XCTAssertTrue([step isKindOfClass:NSDictionary.class]);
    XCTAssertEqual(step.count, 2);
    XCTAssertTrue([operations containsObject:step[@"operation"]]);
    XCTAssertTrue([step[@"selector"] isKindOfClass:NSString.class]);
    XCTAssertGreaterThan([step[@"selector"] length], 0);
    if ([step[@"selector"] hasPrefix:@"text-prefix:"]) {
      XCTAssertTrue([@[@"visible", @"seek", @"playback"] containsObject:step[@"operation"]]);
      XCTAssertGreaterThan([[step[@"selector"] substringFromIndex:@"text-prefix:".length] length], 0);
    }
  }
  XCUIApplication *app = [[XCUIApplication alloc] initWithBundleIdentifier:target];
  XCTAssertTrue(QWQExternalAUTIsActivatableState(app.state));
  NSNumber *before = QWQExternalAUTProcessID(app);
  XCTAssertNotNil(before);
  XCTAssertEqualObjects(before, plan[@"canonicalProcessId"]);
  [app activate];
  XCTAssertTrue([app waitForState:XCUIApplicationStateRunningForeground timeout:10.0]);
  NSMutableArray *observations = [NSMutableArray array];
  for (NSDictionary *step in steps) {
    NSString *operation = step[@"operation"];
    XCTAssertEqualObjects(before, QWQExternalAUTProcessID(app));
    if ([operation isEqualToString:@"back"]) {
      XCUIElement *back = [app.buttons matchingPredicate:[NSPredicate predicateWithFormat:
          @"label == '返回' OR label == 'Back'"]].firstMatch;
      if (back.exists && back.hittable) { [back tap]; }
      else {
        XCUICoordinate *start = [app coordinateWithNormalizedOffset:CGVectorMake(0.01, 0.5)];
        XCUICoordinate *end = [app coordinateWithNormalizedOffset:CGVectorMake(0.8, 0.5)];
        [start pressForDuration:0.1 thenDragToCoordinate:end];
      }
    }
    NSString *selector = step[@"selector"];
    if ([operation isEqualToString:@"reveal"]) {
      for (NSInteger index = 0; index < 30; index++) {
        XCUIElement *candidate = [[app descendantsMatchingType:XCUIElementTypeAny]
            matchingPredicate:[self offlinePredicate:selector]].firstMatch;
        CGRect intersection = CGRectIntersection(candidate.frame, app.windows.firstMatch.frame);
        if (candidate.exists && !CGRectIsEmpty(intersection) && !CGRectIsNull(intersection)) { break; }
        [app swipeUp];
      }
    }
    XCUIElement *element = [self offlineElement:selector app:app];
    XCTAssertFalse(CGRectIsEmpty(element.frame));
    CGRect intersection = CGRectIntersection(element.frame, app.windows.firstMatch.frame);
    XCTAssertFalse(CGRectIsEmpty(intersection) || CGRectIsNull(intersection));
    NSString *observed = [NSString stringWithFormat:@"%@ %@ %@", element.identifier, element.label, element.value ?: @""];
    if ([operation isEqualToString:@"tap"]) {
      XCTAssertTrue(element.hittable); [element tap];
    } else if ([operation isEqualToString:@"scroll"]) {
      [element swipeUp];
    } else if ([operation isEqualToString:@"seek"]) {
      NSInteger previous = [self offlinePlaybackTimes:observed][0].integerValue;
      [element adjustToNormalizedSliderPosition:0.65];
      XCUIElement *updated = [self offlineElement:selector app:app];
      observed = [NSString stringWithFormat:@"%@ %@", updated.label, updated.value ?: @""];
      XCTAssertGreaterThanOrEqual([self offlinePlaybackTimes:observed][0].integerValue, previous + 2);
    } else if ([operation isEqualToString:@"playback"]) {
      NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:180.0];
      NSInteger first = [self offlinePlaybackTimes:observed][0].integerValue;
      XCTAssertLessThanOrEqual(first, 2, @"完整播放必须从开头观察");
      BOOL completed = NO;
      while (deadline.timeIntervalSinceNow > 0) {
        XCUIElement *updated = [self offlineElement:selector app:app];
        observed = [NSString stringWithFormat:@"%@ %@", updated.label, updated.value ?: @""];
        NSArray<NSNumber *> *times = [self offlinePlaybackTimes:observed];
        XCTAssertGreaterThan(times[1].integerValue, 0);
        if (times[0].integerValue >= times[1].integerValue - 1 && times[0].integerValue > first) {
          completed = YES; break;
        }
        [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.15]];
      }
      XCTAssertTrue(completed, @"实际视频未完整播放");
    } else { XCTAssertTrue([@[@"visible", @"back", @"reveal"] containsObject:operation]); }
    [observations addObject:@{@"operation": operation, @"selector": selector, @"observed": observed}];
  }
  XCTAssertEqual(app.state, XCUIApplicationStateRunningForeground);
  NSData *png = app.screenshot.PNGRepresentation;
  XCTAssertGreaterThan(png.length, 32);
  NSNumber *after = QWQExternalAUTProcessID(app);
  XCTAssertEqualObjects(before, after);
  XCTAssertEqual(app.state, XCUIApplicationStateRunningForeground);
  NSString *screenshot = [png base64EncodedStringWithOptions:0];
  for (NSUInteger offset = 0, index = 0; offset < screenshot.length; offset += 3000, index++) {
    NSLog(@"QWQ_OFFLINE_SCREENSHOT %@ %lu %@", plan[@"planDigest"], (unsigned long)index,
        [screenshot substringWithRange:NSMakeRange(offset, MIN(3000, screenshot.length - offset))]);
  }
  NSDictionary *evidence = @{
    @"schema": @"quwoquan_ops.offline_native_page_result.v1", @"caseId": plan[@"caseId"],
    @"planDigest": plan[@"planDigest"], @"platform": @"ios", @"applicationId": target,
    @"processIdBefore": before, @"processIdAfter": after, @"status": @"passed", @"observations": observations,
    @"candidateDigest": plan[@"candidateDigest"], @"artifactDigest": plan[@"artifactDigest"],
    @"deviceId": plan[@"deviceId"], @"launchAttemptId": plan[@"launchAttemptId"],
    @"screenshotDigest": QWQOfflineScreenshotDigest(png), @"screenshotByteLength": @(png.length),
  };
  NSData *data = [NSJSONSerialization dataWithJSONObject:evidence options:NSJSONWritingSortedKeys error:nil];
  NSLog(@"QWQ_OFFLINE_PAGE %@", [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]);
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
