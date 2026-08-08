import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/presentation/video_editor_page.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

void main() {
  testWidgets('视频编辑页在本地视频不可读时由宿主导航返回', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        // 视频编辑页已是 Consumer：先封死 App↔Cloud 边界，本用例只验证本地
        // 探针失败后的错误态，不应触达任何远端读写面。
        overrides: sealedCloudBoundaryOverrides(),
        child: CupertinoApp(
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
      ),
    );

    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.byType(AppPageErrorState), findsOneWidget);
    expect(find.text(SearchText.recoveryReloadLaterTitle), findsOneWidget);
    expect(find.text(ContentText.back), findsNothing);
    expect(find.byIcon(CupertinoIcons.chevron_left), findsOneWidget);
    expect(find.text(SearchText.reload), findsOneWidget);
  });
}

Future<bool> _alwaysUnreadyVideo(String path) async => false;
