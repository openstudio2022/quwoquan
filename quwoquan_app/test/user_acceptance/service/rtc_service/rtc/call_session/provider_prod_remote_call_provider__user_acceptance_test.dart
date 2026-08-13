// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
// readiness_case: call_session_one_to_one_app_uat
/// Production Provider two-device journey.
///
/// The callee must be backgrounded before call creation. It reaches the
/// incoming page only by opening the OS-delivered call presentation; this test
/// never navigates directly to the incoming-call route.
///
/// spec_ref: specs/feature-tree/chat-conversation/realtime-call/one-to-one-call/spec.md#gwt-003
/// spec_ref: specs/feature-tree/chat-conversation/realtime-call/media-infrastructure/spec.md#gwt-004
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/widgets.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/incoming_call_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/outgoing_call_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/video_call_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/pip_call_overlay.dart';

const _apiContractEnv = String.fromEnvironment(
  'API_CONTRACT_ENV',
  defaultValue: 'prod',
);
const _role = String.fromEnvironment('QWQ_PROVIDER_UAT_ROLE');
const _phase = String.fromEnvironment('QWQ_PROVIDER_UAT_PHASE');
const _callId = String.fromEnvironment('QWQ_PROVIDER_UAT_CALL_ID');
const _expectedCallerName = String.fromEnvironment(
  'QWQ_PROVIDER_UAT_EXPECTED_CALLER_NAME',
);

void main() {
  patrolTest(
    'Prod Remote 双向来电通过真实系统展示、媒体、屏幕共享和 PiP 挂断',
    tags: const ['provider', 'rtc', 'two-device'],
    skip: !kRunPatrolAcceptance,
    config: PatrolTesterConfig(visibleTimeout: const Duration(seconds: 30)),
    ($) async {
      expect(_apiContractEnv, 'prod');
      expect(_role == 'caller' || _role == 'callee', isTrue);
      expect(_phase == 'ios_to_android' || _phase == 'android_to_ios', isTrue);
      if (_role == 'caller') {
        expect(_callId.trim(), isNotEmpty);
        await _runCaller($);
      } else {
        expect(_expectedCallerName.trim(), isNotEmpty);
        await _runCallee($);
      }
    },
  );
}

Future<void> _runCaller(PatrolIntegrationTester $) async {
  await launchPatrolAppOnce($);
  await patrolGoTo($, AppRoutePaths.rtcOutgoing(callId: _callId));
  await $(
    find.byType(OutgoingCallPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  await _grantMediaPermissions($);
  await $(
    find.byType(VideoCallPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 120));
  _printMarker('QWQ_PROVIDER_UAT_REMOTE_MEDIA_CONNECTED');

  // Android is the caller in the reverse direction, so it closes the iOS
  // PushKit/CallKit journey after the callee has joined.
  if (_phase == 'android_to_ios') {
    await $.pump(const Duration(seconds: 5));
    await $(find.byType(VideoCallPage)).tap();
    await $(find.text(CallText.callHangup)).tap();
  }
  await _expectCallEnded($);
}

Future<void> _runCallee(PatrolIntegrationTester $) async {
  await launchPatrolAppOnce($);
  await $(
    find.byType(WidgetsApp),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  await $.platform.mobile.pressHome();
  // The Python orchestrator creates the call only after this marker.
  // ignore: avoid_print
  print('QWQ_PROVIDER_UAT_REMOTE_CALLEE_READY:$_phase:callee');

  await _openNativeIncomingCall($);
  _printMarker('QWQ_PROVIDER_UAT_REMOTE_PUSH_PRESENTED');
  await $(
    find.byType(IncomingCallPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 45));
  await $(find.text(CallText.callAccept)).tap();
  await _grantMediaPermissions($);
  await $(
    find.byType(VideoCallPage),
  ).waitUntilVisible(timeout: const Duration(seconds: 120));
  _printMarker('QWQ_PROVIDER_UAT_REMOTE_MEDIA_CONNECTED');

  // Android receives the iOS caller's FCM path. It must exercise real screen
  // sharing and then the in-app PiP hangup before the caller can complete.
  if (_phase == 'ios_to_android') {
    await _exerciseAndroidScreenShareAndPipHangup($);
  }
  await _expectCallEnded($);
}

Future<void> _openNativeIncomingCall(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 75));
  var matched = false;
  while (DateTime.now().isBefore(deadline) && !matched) {
    final notifications = await $.platform.mobile.getNotifications();
    matched = notifications.any(
      (notification) =>
          notification.title.contains(_expectedCallerName) ||
          notification.content.contains(_expectedCallerName),
    );
    if (!matched) {
      await Future<void>.delayed(const Duration(milliseconds: 500));
    }
  }
  expect(
    matched,
    isTrue,
    reason:
        'the physical device must receive the caller-correlated PushKit/CallKit or FCM call presentation',
  );
  await $.platform.mobile.openNotifications();
  await $.platform.mobile.tapOnNotificationBySelector(
    Selector(textContains: _expectedCallerName),
  );
}

Future<void> _exerciseAndroidScreenShareAndPipHangup(
  PatrolIntegrationTester $,
) async {
  await $(find.byType(VideoCallPage)).tap();
  await $(find.text(CallText.callShareScreen)).tap();
  await _grantMediaPermissions($);
  await $(
    find.text(CallText.callScreenSharing),
  ).waitUntilVisible(timeout: const Duration(seconds: 45));
  await $(find.text(CallText.callStopScreenSharing)).tap();
  _printMarker('QWQ_PROVIDER_UAT_REMOTE_SCREEN_SHARE_COMPLETED');

  await $.platform.android.pressBack();
  await $(
    find.byType(PipCallOverlay),
  ).waitUntilVisible(timeout: const Duration(seconds: 30));
  await $(find.byType(PipCallOverlay)).longPress();
  await $(find.text(CallText.callHangup)).tap();
  _printMarker('QWQ_PROVIDER_UAT_REMOTE_PIP_HANGUP');
}

Future<void> _expectCallEnded(PatrolIntegrationTester $) async {
  final deadline = DateTime.now().add(const Duration(seconds: 90));
  while (DateTime.now().isBefore(deadline)) {
    await $.pump(const Duration(milliseconds: 500));
    if (find.byType(VideoCallPage).evaluate().isEmpty) {
      _printMarker('QWQ_PROVIDER_UAT_REMOTE_CALL_ENDED');
      return;
    }
  }
  fail('Prod Remote call did not reach an ended UI state');
}

Future<void> _grantMediaPermissions(PatrolIntegrationTester $) async {
  for (var attempt = 0; attempt < 3; attempt += 1) {
    if (!await $.platform.mobile.isPermissionDialogVisible(
      timeout: const Duration(seconds: 3),
    )) {
      return;
    }
    await $.platform.mobile.grantPermissionWhenInUse();
    await $.pump(const Duration(milliseconds: 500));
  }
}

void _printMarker(String marker) {
  // ignore: avoid_print
  print('$marker:$_role:$_phase');
}
