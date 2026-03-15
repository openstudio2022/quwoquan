import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:url_launcher/url_launcher.dart' as launcher;

/// Navigates to in-app pages via internal routes or external apps via
/// URL Scheme / Universal Links.
class DeepLinkTool implements AssistantTool {
  @override
  String get name => 'deep_link';

  @override
  String get description =>
      'Navigate to an in-app page or open an external app via deep link.';

  static const Set<String> _allowedSchemes = {
    'https',
    'http',
    'quwoquan',
    'maps',
    'tel',
    'sms',
    'mailto',
  };

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final url = (arguments['url'] as String?)?.trim() ?? '';
    if (url.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: '缺少 url 参数',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    final uri = Uri.tryParse(url);
    if (uri == null) {
      return AssistantToolResult(
        success: false,
        message: '无效的 URL: $url',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    if (!_allowedSchemes.contains(uri.scheme.toLowerCase())) {
      return AssistantToolResult(
        success: false,
        message: '不支持的 URL scheme: ${uri.scheme}',
        errorCode: AssistantErrorCode.permissionDenied,
      );
    }

    try {
      final canOpen = await launcher.canLaunchUrl(uri);
      if (!canOpen) {
        return AssistantToolResult(
          success: false,
          message: '设备无法打开此链接: $url',
          errorCode: AssistantErrorCode.unsupportedTarget,
          degraded: true,
        );
      }

      final launched = await launcher.launchUrl(
        uri,
        mode: uri.scheme == 'quwoquan'
            ? launcher.LaunchMode.platformDefault
            : launcher.LaunchMode.externalApplication,
      );

      if (!launched) {
        return AssistantToolResult(
          success: false,
          message: '链接打开失败: $url',
          errorCode: AssistantErrorCode.executionFailed,
          degraded: true,
        );
      }

      return AssistantToolResult(
        success: true,
        message: '已打开: $url',
        data: <String, dynamic>{'url': url, 'scheme': uri.scheme},
      );
    } catch (error) {
      return AssistantToolResult(
        success: false,
        message: '打开链接异常: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }
}
