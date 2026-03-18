import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

class ContentShareActionResult {
  const ContentShareActionResult({
    required this.actionId,
    required this.success,
    this.dismissed = false,
    this.message,
    this.savedPath,
  });

  final String actionId;
  final bool success;
  final bool dismissed;
  final String? message;
  final String? savedPath;
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
    try {
      switch (action.id) {
        case 'copy_link':
          await Clipboard.setData(ClipboardData(text: template.deeplink));
          if (context.mounted) {
            AppToast.show(context, UITextConstants.shareLinkCopied);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: true,
            message: UITextConstants.shareLinkCopied,
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
            return ContentShareActionResult(actionId: action.id, success: true);
          }
          if (context.mounted) {
            AppToast.show(context, UITextConstants.shareCancelled);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: false,
            dismissed: true,
            message: UITextConstants.shareCancelled,
          );
        case 'save_poster':
          final savedPath = await _savePoster(template);
          if (context.mounted) {
            AppToast.show(context, UITextConstants.sharePosterSaved);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: true,
            message: UITextConstants.sharePosterSaved,
            savedPath: savedPath,
          );
        default:
          if (context.mounted) {
            AppToast.show(context, UITextConstants.operationFailed);
          }
          return ContentShareActionResult(
            actionId: action.id,
            success: false,
            message: UITextConstants.operationFailed,
          );
      }
    } catch (_) {
      if (context.mounted) {
        AppToast.show(context, UITextConstants.shareFailed);
      }
      return ContentShareActionResult(
        actionId: action.id,
        success: false,
        message: UITextConstants.shareFailed,
      );
    }
  }

  String _shareTextFor(ContentShareTemplate template) {
    return <String>[
      template.shareTitle,
      if (template.shareSummary.trim().isNotEmpty) template.shareSummary.trim(),
      template.deeplink,
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
        Colors.white,
        accent.withValues(alpha: 0.08),
      ]);
    canvas.drawRect(rect, background);

    canvas.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(56, 56, width - 112, height - 112),
        const Radius.circular(48),
      ),
      Paint()..color = Colors.white.withValues(alpha: 0.92),
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
        color: Colors.black54,
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
        color: Colors.black87,
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
        color: Colors.black87,
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
        const Radius.circular(32),
      ),
      Paint()..color = Colors.grey.shade100,
    );
    _paintText(
      canvas,
      template.deeplink,
      Offset(128, deeplinkTop + 48),
      style: const TextStyle(
        fontSize: AppTypography.sharePosterDeeplink,
        height: AppTypography.bodyLineHeight,
        color: Colors.black87,
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
        color: Colors.black54,
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
    final dir = await getTemporaryDirectory();
    final file = File(
      '${dir.path}/share_${template.profileId}_${DateTime.now().millisecondsSinceEpoch}.png',
    );
    await file.writeAsBytes(bytes.buffer.asUint8List(), flush: true);
    return file.path;
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
