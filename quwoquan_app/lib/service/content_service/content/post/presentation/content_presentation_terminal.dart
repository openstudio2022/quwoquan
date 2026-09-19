import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/di/navigation/content_open_surface_navigation.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ContentUiSurface;

/// 云物化目的面无法消费时的 typed 终态。
///
/// 只隔离被点的这一项：列表其余项保持可浏览，也不显示「内容已删除」或默认
/// 封面卡。[openSurface] 缺席表示信封没带目的面（能力声明与交付不一致）。
Future<void> showContentPresentationUnsupportedTerminal(
  BuildContext context, {
  required String objectId,
  ContentUiSurface? openSurface,
}) async {
  final failure = ContentOpenSurfaceNavigation.unsupportedFailure(
    contractChanged: openSurface == null,
    objectId: objectId,
    openSurface: openSurface,
  );
  if (!context.mounted) {
    return;
  }
  await AppActionErrorFeedback.show(
    context,
    semantic: runtimeErrorSemantic(
      context,
      error: failure,
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.global,
    ),
    semanticIdentifier: 'content-presentation-unsupported',
  );
}
