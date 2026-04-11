/// Thin wrapper for tool `execute` entry (S-LLM): keeps JSON shape as [Map] while
/// centralizing common field reads without changing wire contracts.
class AssistantToolArgumentsMap {
  const AssistantToolArgumentsMap(this.raw);

  final Map<String, dynamic> raw;

  String? stringField(String key) => (raw[key] as String?)?.trim();
}

class AssistantToolCall {
  const AssistantToolCall({
    required this.name,
    required this.arguments,
    this.id = '',
  });

  final String name;
  final Map<String, dynamic> arguments;
  /// OpenAI function calling 协议中的 tool_call id，用于构建 tool message。
  final String id;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'name': name,
      'arguments': arguments,
    };
  }

  factory AssistantToolCall.fromJson(Map<String, dynamic> json) {
    return AssistantToolCall(
      name: (json['name'] as String?)?.trim() ?? '',
      arguments: Map<String, dynamic>.from(
        json['arguments'] as Map? ?? const <String, dynamic>{},
      ),
    );
  }
}

enum AssistantErrorCode {
  none,
  invalidArguments,
  toolNotFound,
  skillNotFound,
  unsupportedTarget,
  permissionDenied,
  networkUnavailable,
  executionFailed,
  unauthorized,
  rateLimited,
}

class AssistantErrorCatalog {
  const AssistantErrorCatalog._();

  static String fallbackMessage(AssistantErrorCode code) {
    switch (code) {
      case AssistantErrorCode.invalidArguments:
        return '请求参数不完整，已自动降级为安全回复。';
      case AssistantErrorCode.toolNotFound:
        return '未找到所需能力，已降级为本地说明。';
      case AssistantErrorCode.skillNotFound:
        return '未找到对应技能，请检查技能是否已启用。';
      case AssistantErrorCode.unsupportedTarget:
        return '当前设备不支持该能力目标，已尝试可用路径。';
      case AssistantErrorCode.permissionDenied:
        return '系统权限不足，暂无法执行该操作。';
      case AssistantErrorCode.networkUnavailable:
        return '当前网络不可用，已切换为离线策略。';
      case AssistantErrorCode.executionFailed:
        return '能力执行失败，已返回可恢复结果。';
      case AssistantErrorCode.unauthorized:
        return '鉴权失败，请检查令牌配置。';
      case AssistantErrorCode.rateLimited:
        return '请求过于频繁，请稍后再试。';
      case AssistantErrorCode.none:
        return '执行成功。';
    }
  }
}

class AssistantToolResult {
  const AssistantToolResult({
    required this.success,
    required this.message,
    this.data,
    this.errorCode = AssistantErrorCode.none,
    this.degraded = false,
  });

  final bool success;
  final String message;
  final Map<String, dynamic>? data;
  final AssistantErrorCode errorCode;
  final bool degraded;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'success': success,
      'message': message,
      'data': data,
      'errorCode': errorCode.name,
      'degraded': degraded,
    };
  }

  factory AssistantToolResult.fromJson(Map<String, dynamic> json) {
    final codeName = (json['errorCode'] as String?)?.trim() ?? 'none';
    final code = AssistantErrorCode.values.firstWhere(
      (e) => e.name == codeName,
      orElse: () => AssistantErrorCode.none,
    );
    return AssistantToolResult(
      success: json['success'] == true,
      message: (json['message'] as String?) ?? '',
      data: (json['data'] as Map?)?.cast<String, dynamic>(),
      errorCode: code,
      degraded: json['degraded'] == true,
    );
  }
}

abstract class AssistantTool {
  String get name;
  String get description;

  Future<AssistantToolResult> execute(Map<String, dynamic> arguments);
}
