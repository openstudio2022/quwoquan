import 'package:quwoquan_app/personal_assistant/intent_bridge/method_channel_adapter.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

/// Creates, queries, and modifies calendar events and reminders via native APIs
/// (iOS EventKit / Android AlarmManager).
class SchedulerTool implements AssistantTool {
  SchedulerTool(this._channelAdapter);

  final MethodChannelAdapter _channelAdapter;

  @override
  String get name => 'scheduler';

  @override
  String get description =>
      'Create, query, or modify calendar events and reminders on the device.';

  @override
  Future<AssistantToolResult> execute(Map<String, dynamic> arguments) async {
    final action = (arguments['action'] as String?)?.trim() ?? '';
    if (action.isEmpty) {
      return const AssistantToolResult(
        success: false,
        message: '缺少 action 参数（create / query / update / delete）',
        errorCode: AssistantErrorCode.invalidArguments,
      );
    }

    try {
      final result = await _channelAdapter.invoke(
        'scheduler_$action',
        <String, dynamic>{
          'title': (arguments['title'] as String?)?.trim() ?? '',
          'startTime': arguments['startTime'] ?? '',
          'endTime': arguments['endTime'] ?? '',
          'allDay': arguments['allDay'] == true,
          'reminder': arguments['reminder'] ?? '',
          'notes': (arguments['notes'] as String?)?.trim() ?? '',
          'eventId': arguments['eventId'] ?? '',
          'query': (arguments['query'] as String?)?.trim() ?? '',
          'rangeStart': arguments['rangeStart'] ?? '',
          'rangeEnd': arguments['rangeEnd'] ?? '',
        },
      );

      if (result.containsKey('error')) {
        return AssistantToolResult(
          success: false,
          message: '日程操作失败: ${result['error']}',
          errorCode: AssistantErrorCode.executionFailed,
          degraded: true,
        );
      }

      return AssistantToolResult(
        success: true,
        message: _actionSummary(action, result),
        data: result,
      );
    } catch (error) {
      return AssistantToolResult(
        success: false,
        message: '日程操作异常: $error',
        errorCode: AssistantErrorCode.executionFailed,
        degraded: true,
      );
    }
  }

  String _actionSummary(String action, Map<String, dynamic> result) {
    switch (action) {
      case 'create':
        return '已创建日程: ${result['title'] ?? ''}';
      case 'query':
        final count = (result['events'] as List?)?.length ?? 0;
        return '查询到 $count 条日程';
      case 'update':
        return '已更新日程';
      case 'delete':
        return '已删除日程';
      default:
        return '日程操作完成';
    }
  }
}
