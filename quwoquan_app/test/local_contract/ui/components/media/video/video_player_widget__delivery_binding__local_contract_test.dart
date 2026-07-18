import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/video/player/video_player_widget.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';

void main() {
  final delivery =
      MediaDeliveryResolver(
        MediaEndpointConfig(
          avatarBaseUrl: 'https://alpha-avatar.quwoquan-env.test:17100',
          imageBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
          videoBaseUrl: 'https://alpha-video.quwoquan-env.test:17100',
          attachmentBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
        ),
      ).resolve(
        'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
        kind: MediaDeliveryKind.video,
        assetId: 'video-primary-0001',
        version: 1,
      );

  tearDown(VideoPlayerWidget.debugResetControllerSlots);

  test('debug 槽位钩子可重置', () {
    VideoPlayerWidget.debugResetControllerSlots();
    expect(VideoPlayerWidget.debugActiveControllerCount, 0);
  });

  testWidgets('dispose 后并发槽位归零', (tester) async {
    VideoPlayerWidget.debugResetControllerSlots();
    final container = ProviderContainer();
    addTearDown(() {
      container.dispose();
      VideoPlayerWidget.debugResetControllerSlots();
    });

    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: ScreenUtilInit(
          designSize: const Size(390, 844),
          builder: (_, _) => CupertinoApp(
            home: SizedBox(
              width: 390,
              height: 220,
              child: VideoPlayerWidget(
                deliveryReference: delivery,
                initialize: true,
                autoPlay: false,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    // 初始化可能已占用槽
    final during = VideoPlayerWidget.debugActiveControllerCount;
    expect(during, anyOf(0, 1, 2));

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    container.dispose();
    await tester.pump();

    expect(
      VideoPlayerWidget.debugActiveControllerCount,
      0,
      reason: 'dispose 后不得泄漏控制器槽',
    );
  });

  test('VideoPlayerWidget API 仅暴露 deliveryReference', () {
    // 编译期契约：构造函数需要 MediaDeliveryReference；运行时抽检字段。
    final widget = VideoPlayerWidget(deliveryReference: delivery);
    expect(widget.deliveryReference.kind, MediaDeliveryKind.video);
    expect(widget.deliveryReference.url, contains('video-primary-0001'));
  });
}
