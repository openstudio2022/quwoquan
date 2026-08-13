import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

/// 评论点赞/踩等轻量互动失败的统一轻反馈。
///
/// provider 侧失败会回滚乐观态并 rethrow；这里兜底捕获并用统一恢复语义的
/// 轻提示告知用户互动未生效，避免异常泄漏为 unhandled zone error、
/// 用户只看到状态无声弹回。
Future<void> runCommentReactionWithFeedback(
  BuildContext context,
  Future<void> Function() reaction,
) async {
  try {
    await reaction();
  } catch (error) {
    if (!context.mounted) {
      return;
    }
    final semantic = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.global,
      allowRetry: false,
    );
    AppToast.showError(context, semantic);
  }
}
