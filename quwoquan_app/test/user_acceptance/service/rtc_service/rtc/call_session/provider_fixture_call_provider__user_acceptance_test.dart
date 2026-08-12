// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:patrol/patrol.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import '../../../../../support/runtime/patrol/patrol_test_support.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/incoming_call_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/outgoing_call_page.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/video_call_page.dart';

const _role = String.fromEnvironment('QWQ_PROVIDER_UAT_ROLE');
const _callId = String.fromEnvironment('QWQ_PROVIDER_UAT_CALL_ID');

void main() {
  patrolTest(
    '两设备 Remote 通话经替代 Provider 完成建连与挂断',
    tags: const ['provider', 'rtc', 'two-device'],
    skip: !kRunPatrolAcceptance,
    ($) async {
      expect(_callId.trim(), isNotEmpty);
      expect(_role == 'caller' || _role == 'callee', isTrue);
      await launchPatrolAppOnce($);

      if (_role == 'caller') {
        await patrolGoTo($, AppRoutePaths.rtcOutgoing(callId: _callId));
        await $(
          find.byType(OutgoingCallPage),
        ).waitUntilVisible(timeout: const Duration(seconds: 30));
        await _grantMediaPermissions($);
      } else {
        await patrolGoTo($, AppRoutePaths.rtcIncoming(callId: _callId));
        await $(
          find.byType(IncomingCallPage),
        ).waitUntilVisible(timeout: const Duration(seconds: 30));
        await $(find.text(CallText.callAccept)).tap();
        await _grantMediaPermissions($);
      }

      await $(
        find.byType(VideoCallPage),
      ).waitUntilVisible(timeout: const Duration(seconds: 120));
      // ignore: avoid_print
      print('QWQ_PROVIDER_UAT_FIXTURE_MEDIA_CONNECTED:$_role:$_callId');

      if (_role == 'caller') {
        await $.pump(const Duration(seconds: 5));
        await $(find.text(CallText.callHangup)).tap();
      }

      final deadline = DateTime.now().add(const Duration(seconds: 60));
      while (DateTime.now().isBefore(deadline)) {
        await $.pump(const Duration(milliseconds: 500));
        if (find.byType(VideoCallPage).evaluate().isEmpty) {
          // ignore: avoid_print
          print('QWQ_PROVIDER_UAT_FIXTURE_CALL_ENDED:$_role:$_callId');
          return;
        }
      }
      fail('fixture Provider call did not reach an ended UI state');
    },
  );
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
