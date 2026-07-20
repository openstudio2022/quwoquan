import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/pages/outgoing_call_page.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';

import '../../../../support/runtime_failure_fixtures.dart';

class _NoopCallTimerNotifier extends CallTimerNotifier {
  @override
  CallTimerState build() => const CallTimerState();

  @override
  void start() {
    state = state.copyWith(isRunning: true);
  }

  @override
  void stop() {
    state = state.copyWith(isRunning: false);
  }

  @override
  void reset() {
    state = const CallTimerState();
  }
}

class _ErrorCallSessionNotifier extends CallSessionNotifier {
  @override
  CallSessionState build() {
    return CallSessionState(
      status: CallStatus.connecting,
      failure: testRuntimeFailure(
        code: 'RTC.SYSTEM.call_signaling_unavailable',
      ),
    );
  }
}

void main() {
  group('OutgoingCallPage', () {
    testWidgets('production UI renders call stage without debug simulation', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
          ],
          child: const MaterialApp(home: OutgoingCallPage(callId: 'call-001')),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.callOutgoingCalling), findsOneWidget);
      expect(
        find.text(UITextConstants.callDebugAutoConnectInFiveSeconds),
        findsNothing,
      );
      expect(find.text(UITextConstants.callDebugManualAnswer), findsNothing);
      expect(find.text(UITextConstants.callDebugTimeout), findsNothing);
      expect(find.text(UITextConstants.cancel), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 2));
    });

    testWidgets('missing participant data uses a safe semantic fallback', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
          ],
          child: const MaterialApp(
            home: OutgoingCallPage(callId: 'call-missing'),
          ),
        ),
      );
      await tester.pump();

      expect(find.text(UITextConstants.user), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 2));
    });

    testWidgets('signaling failure renders a recoverable page error', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
            callSessionProvider.overrideWith(_ErrorCallSessionNotifier.new),
          ],
          child: const MaterialApp(
            home: OutgoingCallPage(callId: 'call-failed'),
          ),
        ),
      );
      await tester.pump();

      expect(find.byType(AppPageErrorState), findsOneWidget);
    });
  });
}
