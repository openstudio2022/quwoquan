import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/rtc/livekit_room_service.dart';
import 'package:quwoquan_app/cloud/services/rtc/rtc_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';
import 'package:quwoquan_app/ui/rtc/pages/outgoing_call_page.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_timer_provider.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_session_provider.dart';

class _NoopLiveKitRoomService extends LiveKitRoomService {
  @override
  Future<void> dispose() async {}
}

class _MockAppDataSourceModeNotifier extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.mock;
}

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

void main() {
  group('OutgoingCallPage — 渲染契约', () {
    testWidgets('开发态显示 5 秒自动接通开关与手动调试按钮', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            rtcRepositoryProvider.overrideWithValue(MockRtcRepository()),
            liveKitRoomServiceProvider.overrideWithValue(
              _NoopLiveKitRoomService(),
            ),
            callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
          ],
          child: const MaterialApp(
            home: OutgoingCallPage(callId: 'call_001'),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('5 秒自动接通'), findsOneWidget);
      expect(find.text('手动接通'), findsOneWidget);
      expect(find.text('拒接'), findsOneWidget);
      expect(find.text('超时'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 2));
    });
  });

  group('OutgoingCallPage — 交互契约', () {
    testWidgets('关闭自动接通后仍可看到手动调试按钮', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            rtcRepositoryProvider.overrideWithValue(MockRtcRepository()),
            liveKitRoomServiceProvider.overrideWithValue(
              _NoopLiveKitRoomService(),
            ),
            callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
          ],
          child: const MaterialApp(
            home: OutgoingCallPage(callId: 'call_001'),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      await tester.tap(find.byType(CupertinoSwitch).first);
      await tester.pump();

      expect(find.text('手动接通'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 2));
    });
  });

  group('OutgoingCallPage — 错误态渲染', () {
    testWidgets('无参与者信息时仍安全显示调试区', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            appDataSourceModeProvider.overrideWith(
              _MockAppDataSourceModeNotifier.new,
            ),
            rtcRepositoryProvider.overrideWithValue(MockRtcRepository()),
            liveKitRoomServiceProvider.overrideWithValue(
              _NoopLiveKitRoomService(),
            ),
            callTimerProvider.overrideWith(_NoopCallTimerNotifier.new),
          ],
          child: const MaterialApp(
            home: OutgoingCallPage(callId: 'call_missing'),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 200));

      expect(find.text('正在呼叫...'), findsOneWidget);
      expect(find.text('5 秒自动接通'), findsOneWidget);

      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump(const Duration(seconds: 2));
    });
  });
}
