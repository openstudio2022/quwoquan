import 'package:quwoquan_app/assistant/contracts/app_action_contract.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart' as launcher;

class AppActionTool implements AssistantTool {
  @override
  String get name => 'app_action';

  @override
  String get description =>
      'Execute typed app actions and return structured outcomes.';

  @override
  Future<AssistantToolResult> execute(AssistantToolArguments arguments) async {
    final request = AppActionRequest.fromJson(arguments.toDynamicJson());

    try {
      switch (request.actionType) {
        case AppActionType.dial:
          return _dial(request);
        case AppActionType.share:
          return _share(request);
        case AppActionType.openConversation:
          return _requiresUserAction(
            request,
            missingTool: 'in_app_navigation',
            suggestedAlternative: '当前运行时未接入会话打开执行器，请在应用内手动进入对应聊天。',
          );
        case AppActionType.sendMessage:
          return _requiresUserAction(
            request,
            missingTool: 'message_sender',
            suggestedAlternative: '当前运行时未接入消息发送执行器，请确认内容后手动发送。',
          );
        case AppActionType.openPost:
          return _requiresUserAction(
            request,
            missingTool: 'in_app_navigation',
            suggestedAlternative: '当前运行时未接入帖子打开执行器，请在应用内手动打开对应内容。',
          );
        case AppActionType.navigateToPage:
          return _requiresUserAction(
            request,
            missingTool: 'in_app_navigation',
            suggestedAlternative: '当前运行时未接入页面跳转执行器，请在应用内手动前往目标页面。',
          );
        case AppActionType.capturePhoto:
          return _requiresUserAction(
            request,
            missingTool: 'camera_capture',
            missingPermission: 'camera',
            suggestedAlternative: '请先授权相机，或手动拍照后继续。',
          );
        case AppActionType.pickPhoto:
          return _requiresUserAction(
            request,
            missingTool: 'photo_picker',
            missingPermission: 'photos',
            suggestedAlternative: '请先授权相册访问，或手动选择照片后继续。',
          );
      }
    } catch (error) {
      return AssistantToolResult(
        success: false,
        message: '操作执行异常: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
        data: AssistantToolResultData.fromJson(
          const AppActionResult(
            assessment: AppActionAssessment.unsupportedAction,
            executed: false,
          ).toJson(),
        ),
        runtimeFailure: assistantToolRuntimeFailure(
          errorCode: AssistantErrorCode.executionFailed,
          message: '操作执行异常: $error',
          functionModule: name,
          stage: 'unexpected_exception',
        ),
      );
    }
  }

  Future<AssistantToolResult> _dial(AppActionRequest request) {
    final phone = _firstNonEmpty(<Object?>[
      request.args.fields['phone'],
      request.args.fields['phoneNumber'],
    ]);
    if (phone.isEmpty) {
      return Future.value(
        _toolFailure(
          message: '拨号缺少电话号码',
          errorCode: AssistantErrorCode.invalidArguments,
          result: const AppActionResult(
            assessment: AppActionAssessment.unsupportedAction,
            executed: false,
          ),
        ),
      );
    }
    return _launchUri(
      Uri(scheme: 'tel', path: phone),
      successMessage: '已打开拨号',
    );
  }

  Future<AssistantToolResult> _share(AppActionRequest request) async {
    final text = _firstNonEmpty(<Object?>[
      request.args.fields['text'],
      request.args.fields['shareText'],
      request.args.fields['url'],
    ]);
    if (text.isEmpty) {
      return _toolFailure(
        message: '分享缺少可用内容',
        errorCode: AssistantErrorCode.invalidArguments,
        result: const AppActionResult(
          assessment: AppActionAssessment.unsupportedAction,
          executed: false,
        ),
      );
    }

    final result = await SharePlus.instance.share(
      ShareParams(
        text: text,
        subject: _firstNonEmpty(<Object?>[
          request.args.fields['subject'],
          request.args.fields['title'],
        ]),
      ),
    );
    if (result.status == ShareResultStatus.success) {
      return _toolSuccess(
        message: '已触发系统分享',
        result: AppActionResult(
          assessment: AppActionAssessment.canExecuteWithTools,
          executed: true,
          result: AppActionArgs(<String, Object?>{
            'status': result.status.name,
            'text': text,
          }),
        ),
      );
    }
    return _toolSuccess(
      message: '用户取消了分享',
      result: AppActionResult(
        assessment: AppActionAssessment.requiresUserAction,
        executed: false,
        suggestedAlternative: '如需继续，请重新确认分享目标。',
        result: AppActionArgs(<String, Object?>{'status': result.status.name}),
      ),
    );
  }

  Future<AssistantToolResult> _launchUri(
    Uri uri, {
    required String successMessage,
  }) async {
    final canOpen = await launcher.canLaunchUrl(uri);
    if (!canOpen) {
      return _toolFailure(
        message: '设备不支持当前操作',
        errorCode: AssistantErrorCode.unsupportedTarget,
        result: const AppActionResult(
          assessment: AppActionAssessment.requiresUserAction,
          executed: false,
        ),
      );
    }
    final ok = await launcher.launchUrl(uri);
    if (!ok) {
      return _toolFailure(
        message: '操作执行失败',
        errorCode: AssistantErrorCode.executionFailed,
        result: const AppActionResult(
          assessment: AppActionAssessment.canExecuteWithTools,
          executed: false,
        ),
      );
    }

    return _toolSuccess(
      message: successMessage,
      result: AppActionResult(
        assessment: AppActionAssessment.canExecuteWithTools,
        executed: true,
        result: AppActionArgs(<String, Object?>{'uri': uri.toString()}),
      ),
    );
  }

  AssistantToolResult _requiresUserAction(
    AppActionRequest request, {
    required String missingTool,
    String missingPermission = '',
    required String suggestedAlternative,
  }) {
    return _toolSuccess(
      message: suggestedAlternative,
      result: AppActionResult(
        assessment: AppActionAssessment.requiresUserAction,
        executed: false,
        missingTool: missingTool,
        missingPermission: missingPermission,
        suggestedAlternative: suggestedAlternative,
        result: AppActionArgs(<String, Object?>{
          'actionType': request.actionType.wireName,
          'requiresConfirmation': request.requiresConfirmation,
        }),
      ),
    );
  }

  AssistantToolResult _toolSuccess({
    required String message,
    required AppActionResult result,
  }) {
    return AssistantToolResult(
      success: true,
      message: message,
      data: AssistantToolResultData.fromJson(result.toJson()),
    );
  }

  AssistantToolResult _toolFailure({
    required String message,
    required AssistantErrorCode errorCode,
    required AppActionResult result,
  }) {
    return AssistantToolResult(
      success: false,
      message: message,
      errorCode: errorCode,
      degraded: true,
      data: AssistantToolResultData.fromJson(result.toJson()),
      runtimeFailure: assistantToolRuntimeFailure(
        errorCode: errorCode,
        message: message,
        functionModule: name,
      ),
    );
  }

  String _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = value?.toString().trim() ?? '';
      if (text.isNotEmpty) {
        return text;
      }
    }
    return '';
  }
}
