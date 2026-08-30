/// 设备推送 tap 直达路由契约：conversation 语义锚点分发到 chatDetail、
/// 来电帧不进入通用分发、目标缺失静默忽略、平台能力不可用时一致降级。
///
/// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#req-003
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/navigation/push_tap_navigation.dart';
import 'package:quwoquan_app/runtime/platform/firebase_incoming_call_runtime.dart';

final class _ScriptedPushTapIntentSource implements PushTapIntentSource {
  _ScriptedPushTapIntentSource({this.initialIntent, this.available = true});

  final PushTapIntent? initialIntent;
  final bool available;
  void Function(PushTapIntent intent)? onIntent;
  var startCount = 0;
  var stopCount = 0;

  @override
  Future<void> start(void Function(PushTapIntent intent) onIntent) async {
    startCount += 1;
    if (!available) {
      return;
    }
    this.onIntent = onIntent;
    final initial = initialIntent;
    if (initial != null) {
      onIntent(initial);
    }
  }

  void emit(PushTapIntent intent) => onIntent?.call(intent);

  @override
  Future<void> stop() async {
    stopCount += 1;
    onIntent = null;
  }
}

void main() {
  test('conversation 锚点分发到 chatDetail 且冷启动初始 intent 同链处理', () async {
    final source = _ScriptedPushTapIntentSource(
      initialIntent: const PushTapIntent(
        targetType: 'conversation',
        targetId: 'conv_push_1',
        callId: '',
      ),
    );
    final pushed = <String>[];
    final navigator = PushTapNavigator(intentSource: source, push: pushed.add);
    addTearDown(navigator.dispose);

    await navigator.start();
    expect(pushed, ['/chat/conv_push_1']);

    source.emit(
      const PushTapIntent(
        targetType: 'conversation',
        targetId: 'conv_push_2',
        callId: '',
      ),
    );
    expect(pushed, ['/chat/conv_push_1', '/chat/conv_push_2']);
  });

  test('来电 intent 与未知目标不进入通用分发', () async {
    final source = _ScriptedPushTapIntentSource();
    final pushed = <String>[];
    final navigator = PushTapNavigator(intentSource: source, push: pushed.add);
    addTearDown(navigator.dispose);
    await navigator.start();

    source.emit(
      const PushTapIntent(
        callId: 'call-1',
        targetType: 'conversation',
        targetId: 'conv_push_1',
      ),
    );
    source.emit(
      const PushTapIntent(callId: '', targetType: 'homepage', targetId: 'h1'),
    );
    source.emit(
      const PushTapIntent(callId: '', targetType: 'conversation', targetId: ''),
    );

    expect(pushed, isEmpty);
  });

  test('平台能力不可用时 start 为一致降级 no-op', () async {
    final pushed = <String>[];
    final navigator = PushTapNavigator(intentSource: null, push: pushed.add);
    await navigator.start();
    await navigator.dispose();
    expect(pushed, isEmpty);
  });

  test('source 未配置时不产生 tap intent 且不阻断 Shell', () async {
    final source = _ScriptedPushTapIntentSource(available: false);
    final pushed = <String>[];
    final navigator = PushTapNavigator(intentSource: source, push: pushed.add);
    addTearDown(navigator.dispose);

    await expectLater(navigator.start(), completes);

    expect(source.startCount, 1);
    expect(pushed, isEmpty);
  });
}
