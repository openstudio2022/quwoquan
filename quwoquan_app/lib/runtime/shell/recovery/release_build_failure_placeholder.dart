import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

/// release 下替换 Widget 构建异常默认灰屏死块的中性可读占位。
///
/// 只承担用户可见降级：不含堆栈、错误码或任何技术字段；异常本身仍先经
/// `FlutterError.onError` 链完成日志与遥测。可能在无 Directionality /
/// 主题 ancestor 的层级被构建，必须自足。
class ReleaseBuildFailurePlaceholder extends StatelessWidget {
  const ReleaseBuildFailurePlaceholder({super.key});

  @override
  Widget build(BuildContext context) {
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Text(
            SearchText.recoveryInvalidContentTitle,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosToolbarSecondaryIconLight,
            ),
          ),
        ),
      ),
    );
  }
}
