import 'dart:async';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/runtime/platform/temporary_file_writer.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_template.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart';

class ContentShareActionResult {
  const ContentShareActionResult({
    required this.actionId,
    required this.success,
    this.dismissed = false,
    this.message,
    this.savedPath,
    this.destinationKind,
    this.destination,
    this.providerReceiptId,
    this.error,
  });

  final String actionId;
  final bool success;
  final bool dismissed;
  final String? message;
  final String? savedPath;
  final String? destinationKind;
  final String? destination;
  final String? providerReceiptId;
  final Object? error;

  bool get isConfirmedOutboundDelivery =>
      success &&
      (destinationKind?.trim().isNotEmpty ?? false) &&
      (providerReceiptId?.trim().isNotEmpty ?? false);
}

abstract class ContentShareActionHandler {
  Future<ContentShareActionResult> execute(
    BuildContext context,
    ContentShareTemplate template,
    ContentShareAction action,
  );
}

class DefaultContentShareActionHandler implements ContentShareActionHandler {
  const DefaultContentShareActionHandler();

  @override
  Future<ContentShareActionResult> execute(
    BuildContext context,
    ContentShareTemplate template,
    ContentShareAction action,
  ) async {
    // handler 保持 const 可复用；异常端口在任何 await 之前从调用点所在
    // ProviderScope 解析，因此 local_contract 能 override 成测试树内 double。
    final telemetry = ProviderScope.containerOf(
      context,
    ).read(exceptionTelemetryPortProvider);
    try {
      switch (action.id) {
        case 'copy_link':
          await Clipboard.setData(ClipboardData(text: template.landingUrl));
          if (context.mounted) {
            AppToast.show(context, ChatText.shareLinkCopied);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: true,
            message: ChatText.shareLinkCopied,
          );
        case 'system_share':
          final result = await SharePlus.instance.share(
            ShareParams(
              title: template.title,
              subject: template.shareTitle,
              text: _shareTextFor(template),
            ),
          );
          if (result.status == ShareResultStatus.success) {
            final receipt = result.raw.trim();
            if (receipt.isEmpty) {
              throw StateError('system_share_missing_provider_receipt');
            }
            return ContentShareActionResult(
              actionId: action.id,
              success: true,
              destinationKind: 'external_app',
              destination: receipt,
              providerReceiptId: receipt,
            );
          }
          if (context.mounted) {
            AppToast.show(context, ChatText.shareCancelled);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: false,
            dismissed: true,
            message: ChatText.shareCancelled,
          );
        case 'save_poster':
          final savedPath = await _savePoster(template);
          if (context.mounted) {
            AppToast.show(context, ChatText.sharePosterSaved);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: true,
            message: ChatText.sharePosterSaved,
            savedPath: savedPath,
          );
        default:
          if (context.mounted) {
            AppToast.show(context, CreationText.operationFailed);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: false,
            message: CreationText.operationFailed,
          );
      }
    } catch (error, stackTrace) {
      unawaited(
        telemetry.recordHandledException(
          source: 'content.share.${action.id}',
          error: error,
          stackTrace: stackTrace,
        ),
      );
      if (context.mounted) {
        AppToast.show(context, ChatText.shareFailed);
      }
      return ContentShareActionResult(
        actionId: action.id,
        success: false,
        message: ChatText.shareFailed,
        error: error,
      );
    }
  }

  String _shareTextFor(ContentShareTemplate template) {
    return <String>[
      template.shareTitle,
      if (template.shareSummary.trim().isNotEmpty) template.shareSummary.trim(),
      template.landingUrl,
    ].where((line) => line.trim().isNotEmpty).join('\n');
  }

  Future<String> _savePoster(ContentShareTemplate template) async {
    const width = 1080.0;
    const height = 1600.0;
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder);
    final rect = const Rect.fromLTWH(0, 0, width, height);

    final accent = template.profileId == 'moment'
        ? AppColors.secondaryColor
        : AppColors.welcomeBackground;
    final background = Paint()
      ..shader = ui.Gradient.linear(rect.topLeft, rect.bottomRight, <Color>[
        AppColors.white,
        accent.withValues(alpha: 0.08),
      ]);
    canvas.drawRect(rect, background);

    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(56, 56, width - 112, height - 112),
        const Radius.circular(48),
      ),
      Paint()..color = AppColors.white.withValues(alpha: 0.92),
    );

    _paintText(
      canvas,
      template.title,
      const Offset(96, 108),
      style: TextStyle(
        fontSize: AppTypography.sharePosterEyebrow,
        fontWeight: FontWeight.w700,
        color: accent,
      ),
      maxWidth: width - 192,
    );
    _paintText(
      canvas,
      template.subtitle,
      const Offset(96, 182),
      style: TextStyle(
        fontSize: AppTypography.sharePosterSubtitle,
        color: AppColors.black.withValues(alpha: 0.54),
      ),
      maxWidth: width - 192,
    );
    _paintText(
      canvas,
      template.shareTitle,
      const Offset(96, 320),
      style: const TextStyle(
        fontSize: AppTypography.sharePosterHeadline,
        fontWeight: FontWeight.w700,
        color: AppColors.sharePosterInkHighContrast,
      ),
      maxWidth: width - 192,
      maxLines: 3,
    );
    _paintText(
      canvas,
      template.shareSummary,
      const Offset(96, 560),
      style: TextStyle(
        fontSize: AppTypography.sharePosterBody,
        height: AppTypography.lineHeightRelaxed,
        color: AppColors.black.withValues(alpha: 0.87),
      ),
      maxWidth: width - 192,
      maxLines: 6,
    );
    if ((template.notice ?? '').trim().isNotEmpty) {
      _paintText(
        canvas,
        template.notice!.trim(),
        const Offset(96, 900),
        style: TextStyle(
          fontSize: AppTypography.sharePosterSubtitle,
          color: accent,
          fontWeight: FontWeight.w600,
        ),
        maxWidth: width - 192,
        maxLines: 2,
      );
    }

    final deeplinkTop = (template.notice ?? '').trim().isNotEmpty
        ? 1010.0
        : 930.0;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(96, deeplinkTop, width - 192, 240),
        Radius.circular(AppSpacing.radiusThirtyTwo),
      ),
      Paint()..color = AppColors.sharePosterDeeplinkSurface,
    );
    _paintText(
      canvas,
      template.landingUrl,
      Offset(128, deeplinkTop + 48),
      style: const TextStyle(
        fontSize: AppTypography.sharePosterDeeplink,
        height: AppTypography.bodyLineHeight,
        color: AppColors.sharePosterInkHighContrast,
      ),
      maxWidth: width - 256,
      maxLines: 4,
    );
    _paintText(
      canvas,
      '保存于趣窝圈 · ${DateTime.now().toLocal().toIso8601String().substring(0, 16)}',
      const Offset(96, 1360),
      style: TextStyle(
        fontSize: AppTypography.sharePosterMeta,
        color: AppColors.black.withValues(alpha: 0.54),
      ),
      maxWidth: width - 192,
    );

    final image = await recorder.endRecording().toImage(
      width.toInt(),
      height.toInt(),
    );
    final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
    if (bytes == null) {
      throw StateError('poster_render_failed');
    }
    return writeAppTemporaryFileBytes(
      fileName:
          'share_${template.profileId}_${DateTime.now().millisecondsSinceEpoch}.png',
      bytes: bytes.buffer.asUint8List(),
    );
  }

  void _paintText(
    Canvas canvas,
    String text,
    Offset offset, {
    required TextStyle style,
    required double maxWidth,
    int? maxLines,
  }) {
    final painter = TextPainter(
      text: TextSpan(text: text, style: style),
      textDirection: TextDirection.ltr,
      maxLines: maxLines,
      ellipsis: maxLines == null ? null : '...',
    )..layout(maxWidth: maxWidth);
    painter.paint(canvas, offset);
  }
}
