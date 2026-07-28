import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/widgets/app_modal_presenter.dart';

typedef UiErrorActionCallback = Future<void> Function(UiErrorAction action);

/// 非页面阻断动作的统一错误对话框；保留输入现场并只执行 metadata 恢复动作。
class AppActionErrorFeedback {
  const AppActionErrorFeedback._();

  static Future<void> show(
    BuildContext context, {
    required UiErrorSemantic semantic,
    UiErrorActionCallback? onAction,
  }) async {
    final primary = semantic.primaryAction;
    if (!context.mounted) {
      return;
    }
    await showAppCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(semantic.title),
        content: Text(semantic.message),
        actions: <Widget>[
          if (onAction != null && semantic.secondaryAction != null)
            CupertinoDialogAction(
              onPressed: () {
                Navigator.of(dialogContext).pop();
                unawaited(onAction(semantic.secondaryAction!));
              },
              child: Text(semantic.secondaryAction!.label),
            ),
          if (onAction != null && primary != null)
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () {
                Navigator.of(dialogContext).pop();
                unawaited(onAction(primary));
              },
              child: Text(primary.label),
            )
          else if (onAction == null || semantic.secondaryAction == null)
            CupertinoDialogAction(
              isDefaultAction: true,
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text(ContentText.gotIt),
            ),
        ],
      ),
    );
  }
}
