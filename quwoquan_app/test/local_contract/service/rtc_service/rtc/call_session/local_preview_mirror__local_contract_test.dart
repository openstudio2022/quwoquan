// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-012
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-012.t1
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-012.t2
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/call-experience/spec.md#gwt-012.t3
//
// 本地预览前摄镜像契约：
// 本地前置摄像头预览水平镜像（照镜子的业界默认预期）；翻转到后摄与
// 渲染远端参与者画面不镜像。决策单一真相源为 shouldMirrorLocalPreview，
// ParticipantTile / PiP 渲染必须消费同一函数。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/media_device_provider.dart';

void main() {
  test('本地 + 前置摄像头 → 镜像', () {
    expect(
      shouldMirrorLocalPreview(
        isLocal: true,
        cameraPosition: CameraPosition.front,
      ),
      isTrue,
    );
  });

  test('本地 + 后置摄像头 → 不镜像', () {
    expect(
      shouldMirrorLocalPreview(
        isLocal: true,
        cameraPosition: CameraPosition.back,
      ),
      isFalse,
      reason: '翻转到后摄后画面必须回到非镜像',
    );
  });

  test('远端参与者任何摄像头位姿都不镜像', () {
    for (final position in CameraPosition.values) {
      expect(
        shouldMirrorLocalPreview(isLocal: false, cameraPosition: position),
        isFalse,
        reason: '远端画面不得镜像',
      );
    }
  });

  test('翻转摄像头往返镜像决策一致', () {
    var position = CameraPosition.front;
    expect(
      shouldMirrorLocalPreview(isLocal: true, cameraPosition: position),
      isTrue,
    );
    position = position.toggle();
    expect(
      shouldMirrorLocalPreview(isLocal: true, cameraPosition: position),
      isFalse,
    );
    position = position.toggle();
    expect(
      shouldMirrorLocalPreview(isLocal: true, cameraPosition: position),
      isTrue,
    );
  });
}
