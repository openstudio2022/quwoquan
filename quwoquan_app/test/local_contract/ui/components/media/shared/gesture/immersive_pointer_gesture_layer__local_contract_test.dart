import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/shared/gesture/immersive_pointer_gesture_layer.dart';

void main() {
  testWidgets('ImmersivePointerGestureLayer 统一采样单指 delta 与水平速度', (
    tester,
  ) async {
    final starts = <ImmersivePointerGestureStart>[];
    final updates = <ImmersivePointerGestureUpdate>[];
    final ends = <ImmersivePointerGestureEnd>[];

    await tester.pumpWidget(
      CupertinoApp(
        home: SizedBox(
          width: 320,
          height: 480,
          child: ImmersivePointerGestureLayer(
            onStart: starts.add,
            onUpdate: updates.add,
            onEnd: ends.add,
            child: const SizedBox.expand(),
          ),
        ),
      ),
    );

    final gesture = await tester.startGesture(const Offset(160, 240));
    await tester.pump(const Duration(milliseconds: 16));
    await gesture.moveBy(const Offset(-18, 4));
    await tester.pump(const Duration(milliseconds: 16));
    await gesture.up();
    await tester.pump();

    expect(starts, hasLength(1));
    expect(updates, hasLength(1));
    expect(ends, hasLength(1));
    expect(updates.single.startLocalPosition, const Offset(160, 240));
    expect(updates.single.localPosition, const Offset(142, 244));
    expect(updates.single.delta, const Offset(-18, 4));
    expect(updates.single.totalDelta, const Offset(-18, 4));
    expect(updates.single.velocityDx, lessThan(0));
    expect(ends.single.totalDelta, const Offset(-18, 4));
    expect(ends.single.velocityDx, lessThan(0));
  });
}
