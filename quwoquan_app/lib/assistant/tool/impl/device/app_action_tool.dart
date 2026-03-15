import 'package:flutter/services.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:url_launcher/url_launcher.dart' as launcher;

/// Executes device-level actions: phone calls, SMS, email, map navigation,
/// clipboard copy.
class AppActionTool implements AssistantTool {
  @override
  String get name => 'app_action';

  @override
  String get description =>
      'Execute device actions like calling, texting, emailing, navigating, '
      'or copying to clipboard.';

  static const Set<String> _allowedActions = {
    'call',
    'sms',
    'email',
    'navigate',
    'clipboard',
  };

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final action = (arguments['action'] as String?)?.trim() ?? '';
    if (!_allowedActions.contains(action)) {
      return AssistantToolResult(
        success: false,
        message: '不支持的 action: $action（可选: ${_allowedActions.join(", ")}）',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    try {
      switch (action) {
        case 'call':
          return _launchUri('tel', arguments['phone'] as String?);
        case 'sms':
          final phone = (arguments['phone'] as String?)?.trim() ?? '';
          final body = (arguments['body'] as String?)?.trim() ?? '';
          final smsUri = body.isEmpty
              ? Uri(scheme: 'sms', path: phone)
              : Uri(scheme: 'sms', path: phone, queryParameters: {'body': body});
          return _launch(smsUri, '短信');
        case 'email':
          final to = (arguments['to'] as String?)?.trim() ?? '';
          final subject = (arguments['subject'] as String?)?.trim() ?? '';
          final body = (arguments['body'] as String?)?.trim() ?? '';
          final emailUri = Uri(
            scheme: 'mailto',
            path: to,
            queryParameters: <String, String>{
              if (subject.isNotEmpty) 'subject': subject,
              if (body.isNotEmpty) 'body': body,
            },
          );
          return _launch(emailUri, '邮件');
        case 'navigate':
          final address = (arguments['address'] as String?)?.trim() ?? '';
          final lat = arguments['lat'];
          final lng = arguments['lng'];
          Uri mapsUri;
          if (lat != null && lng != null) {
            mapsUri = Uri.parse('https://maps.apple.com/?ll=$lat,$lng&q=$address');
          } else if (address.isNotEmpty) {
            mapsUri = Uri.parse(
              'https://maps.apple.com/?q=${Uri.encodeComponent(address)}',
            );
          } else {
            return const AssistantToolResult(
              success: false,
              message: '导航需要提供 address 或 lat/lng',
              errorCode: AssistantErrorCode.invalidArguments,
            );
          }
          return _launch(mapsUri, '导航');
        case 'clipboard':
          final text = (arguments['text'] as String?)?.trim() ?? '';
          if (text.isEmpty) {
            return const AssistantToolResult(
              success: false,
              message: '缺少要复制的 text',
              errorCode: AssistantErrorCode.invalidArguments,
            );
          }
          await Clipboard.setData(ClipboardData(text: text));
          return AssistantToolResult(
            success: true,
            message: '已复制到剪贴板',
            data: <String, dynamic>{'length': text.length},
          );
        default:
          return const AssistantToolResult(
            success: false,
            message: '未知操作',
            errorCode: AssistantErrorCode.executionFailed,
          );
      }
    } catch (error) {
      return AssistantToolResult(
        success: false,
        message: '操作执行异常: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }

  Future<AssistantToolResult> _launchUri(String scheme, String? value) {
    final clean = (value ?? '').trim();
    if (clean.isEmpty) {
      return Future.value(
        AssistantToolResult(
          success: false,
          message: '缺少 $scheme 参数值',
          errorCode: AssistantErrorCode.invalidArguments,
        ),
      );
    }
    return _launch(Uri(scheme: scheme, path: clean), scheme);
  }

  Future<AssistantToolResult> _launch(Uri uri, String label) async {
    final canOpen = await launcher.canLaunchUrl(uri);
    if (!canOpen) {
      return AssistantToolResult(
        success: false,
        message: '设备不支持此$label操作',
        errorCode: AssistantErrorCode.unsupportedTarget,
        degraded: true,
      );
    }
    final ok = await launcher.launchUrl(uri);
    if (!ok) {
      return AssistantToolResult(
        success: false,
        message: '$label打开失败',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
    return AssistantToolResult(
      success: true,
      message: '已打开$label',
      data: <String, dynamic>{'uri': uri.toString()},
    );
  }
}
