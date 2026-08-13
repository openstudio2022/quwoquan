// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/error-permission-display-semantics/spec.md#gwt-017

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// 沉浸深色上下文失败/等待呈现的语义 token 契约。
///
/// 沉浸面前景不得裸写固定白色：`ImmersiveMediaFailureContent`（Work Browser
/// 图片与视频共用的唯一沉浸失败组件）与沉浸 loading 面必须全部经
/// `AppColors.immersiveForeground` 声明前景语义，防止主题演进时旁路漂移。
void main() {
  String sourceOf(String path) => File(path).readAsStringSync();

  test('共享沉浸失败组件前景全部经 immersiveForeground token 声明', () {
    final source = sourceOf(
      'lib/service/content_service/media/media_asset/presentation/'
      'immersive_media_failure_content.dart',
    );
    expect(source, contains('AppColors.immersiveForeground'));
    // 不允许裸写固定白色（token 定义本身在 design_system，不在此文件）。
    expect(source, isNot(contains('AppColors.white')));
    expect(source, isNot(contains('CupertinoColors.white')));
    expect(source, isNot(contains('Colors.white')));
  });

  test('沉浸 loading 面的等待指示色经语义 token 声明', () {
    // accent 填充按钮内的前景白（如上传/保存按钮 spinner）为合理惯例，
    // 不进入本清单；本清单只收深色沉浸面上的等待指示。
    const immersiveLoadingSurfaces = <String>[
      'lib/service/content_service/media/media_asset/presentation/'
          'image_book_canvas.dart',
      'lib/service/content_service/media/media_asset/presentation/'
          'video_player_surface_builder.dart',
      'lib/service/rtc_service/rtc/call_session/presentation/'
          'video_call_screen_share_surface.dart',
      'lib/service/rtc_service/rtc/call_session/presentation/'
          'call_stage_banner.dart',
    ];
    for (final path in immersiveLoadingSurfaces) {
      final source = sourceOf(path);
      expect(
        source,
        isNot(contains('indicatorColor: AppColors.white')),
        reason: path,
      );
      expect(
        source,
        contains('indicatorColor: AppColors.immersiveForeground'),
        reason: path,
      );
    }
  });
}
