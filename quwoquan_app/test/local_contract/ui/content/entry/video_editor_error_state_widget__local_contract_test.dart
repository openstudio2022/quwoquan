import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/content/entry/pages/video_editor_page.dart';

void main() {
  testWidgets('视频编辑页在本地视频不可读时展示返回与再试一次', (tester) async {
    await tester.pumpWidget(
      CupertinoApp(
        home: VideoEditorPage(
          sourceVideoPath: '/tmp/missing-video.mp4',
          initialVideoPath: '/tmp/missing-video.mp4',
          initialThumbnailPath: '',
          initialDurationMs: 0,
          initialTrimStartMs: 0,
          initialTrimEndMs: 0,
          initialCoverTimeMs: 0,
          initialMuted: false,
          videoFileReadyProbe: _alwaysUnreadyVideo,
        ),
      ),
    );

    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text('视频预览暂不可用'), findsOneWidget);
    expect(find.text(UITextConstants.back), findsOneWidget);
    expect(find.text(UITextConstants.tryAgain), findsOneWidget);
  });
}

Future<bool> _alwaysUnreadyVideo(String path) async => false;
