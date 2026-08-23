import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/recovery_surface_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';

/// 阻断式配置错误页：runtime package 缺失/失效时的唯一去处。
///
/// 与网络/版本恢复页（`StartupRecoveryPage`）职责分离：配置失效意味着
/// Web/更新入口的 URL 本身不可信，因此本页不提供任何依赖 runtime 配置的
/// 外部跳转，只做静态呈现与本地诊断复制，且禁止继续进入业务壳。
class StartupConfigurationErrorPage extends StatelessWidget {
  const StartupConfigurationErrorPage({
    super.key,
    required this.failureCode,
    required this.invalidKeys,
  });

  final String failureCode;
  final List<String> invalidKeys;

  String get _diagnosticText =>
      'failureCode=$failureCode; invalidKeys=${invalidKeys.join(',')}';

  Future<void> _copyDiagnostics(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: _diagnosticText));
    if (context.mounted) {
      AppToast.show(
        context,
        FoundationText.startupConfigErrorCopied,
        tone: UiErrorTone.neutral,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    const colors = AppColorsTheme(isDark: false);
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: SystemUiOverlayStyle.dark.copyWith(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: AppColorsFunctional.getColor(
          false,
          ColorType.surfaceMuted,
        ),
        systemNavigationBarIconBrightness: Brightness.dark,
      ),
      child: AppScaffold(
        backgroundColor: AppColorsFunctional.getColor(
          false,
          ColorType.surfaceMuted,
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: RecoverySurfaceSpacing.horizontalInset,
            ),
            child: Align(
              alignment: const Alignment(
                0,
                RecoverySurfaceSpacing.visualCenterAlignment,
              ),
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxWidth: RecoverySurfaceSpacing.contentMaxWidth,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    Icon(
                      Icons.build_circle_outlined,
                      size: AppSpacing.forty,
                      color: colors.foregroundSecondary,
                    ),
                    const SizedBox(height: RecoverySurfaceSpacing.titleSubtitleGap),
                    Text(
                      FoundationText.startupConfigErrorTitle,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: colors.foregroundPrimary,
                        fontSize: AppTypography.iosProfileTitle,
                        fontWeight: AppTypography.semiBold,
                        height: AppTypography.lineHeightTight,
                      ),
                    ),
                    const SizedBox(height: RecoverySurfaceSpacing.titleSubtitleGap),
                    Text(
                      FoundationText.startupConfigErrorMessage,
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        color: colors.foregroundSecondary,
                        fontSize: AppTypography.iosBody,
                        fontWeight: AppTypography.regular,
                        height: AppTypography.lineHeightRelaxed,
                      ),
                    ),
                    if (invalidKeys.isNotEmpty) ...<Widget>[
                      const SizedBox(
                        height: RecoverySurfaceSpacing.subtitleActionGap,
                      ),
                      _InvalidKeysCard(invalidKeys: invalidKeys, colors: colors),
                    ],
                    if (kDebugMode) ...<Widget>[
                      const SizedBox(
                        height: RecoverySurfaceSpacing.titleSubtitleGap,
                      ),
                      Text(
                        FoundationText.startupConfigErrorDebugRepair,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: colors.foregroundSecondary,
                          fontSize: AppTypography.iosFootnote,
                          fontWeight: AppTypography.regular,
                          height: AppTypography.lineHeightRelaxed,
                        ),
                      ),
                    ],
                    const SizedBox(
                      height: RecoverySurfaceSpacing.subtitleActionGap,
                    ),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton(
                        style: ButtonStyle(
                          minimumSize: const WidgetStatePropertyAll<Size>(
                            Size.fromHeight(AppSpacing.buttonHeight),
                          ),
                          textStyle: const WidgetStatePropertyAll<TextStyle>(
                            TextStyle(
                              fontSize: AppTypography.iosBody,
                              fontWeight: AppTypography.medium,
                            ),
                          ),
                          shape: const WidgetStatePropertyAll<OutlinedBorder>(
                            StadiumBorder(),
                          ),
                          foregroundColor: const WidgetStatePropertyAll<Color>(
                            AppColors.primaryColor,
                          ),
                          side: const WidgetStatePropertyAll<BorderSide>(
                            BorderSide(
                              color: AppColors.primaryColor,
                              width: AppSpacing.one,
                            ),
                          ),
                        ),
                        onPressed: () => _copyDiagnostics(context),
                        child: const Text(
                          FoundationText.startupConfigErrorCopyAction,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _InvalidKeysCard extends StatelessWidget {
  const _InvalidKeysCard({required this.invalidKeys, required this.colors});

  final List<String> invalidKeys;
  final AppColorsTheme colors;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(false, ColorType.surfaceElevated),
        borderRadius: BorderRadius.circular(AppSpacing.sm),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            FoundationText.startupConfigErrorKeysLabel,
            style: TextStyle(
              color: colors.foregroundSecondary,
              fontSize: AppTypography.iosFootnote,
              fontWeight: AppTypography.medium,
            ),
          ),
          const SizedBox(height: AppSpacing.xs),
          for (final key in invalidKeys)
            Text(
              key,
              style: TextStyle(
                color: colors.foregroundPrimary,
                fontSize: AppTypography.iosFootnote,
                fontFamily: 'monospace',
                height: AppTypography.lineHeightRelaxed,
              ),
            ),
        ],
      ),
    );
  }
}
