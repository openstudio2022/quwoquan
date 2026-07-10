/// 云侧随错误响应下发的恢复指令（唯一真相源为 errors.yaml 的 recovery_action /
/// recovery_after_seconds，经 runtime/errors 出口下发）。本类型刻意不依赖
/// runtime_recovery_policy（避免循环依赖）：仅承载原始 action/afterSeconds/
/// disruptionLevel 字符串与整数，由 RuntimeRecoveryPolicy 映射为枚举决策。
class RuntimeRecoveryDirective {
  const RuntimeRecoveryDirective({
    this.action = '',
    this.afterSeconds = 0,
    this.disruptionLevel = '',
  });

  const RuntimeRecoveryDirective.none()
    : action = '',
      afterSeconds = 0,
      disruptionLevel = '';

  factory RuntimeRecoveryDirective.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const RuntimeRecoveryDirective.none();
    final afterRaw = json['afterSeconds'];
    final afterSeconds = afterRaw is num
        ? afterRaw.toInt()
        : int.tryParse('${afterRaw ?? ''}') ?? 0;
    return RuntimeRecoveryDirective(
      action: ((json['action'] as String?) ?? '').trim(),
      afterSeconds: afterSeconds < 0 ? 0 : afterSeconds,
      disruptionLevel: ((json['disruptionLevel'] as String?) ?? '').trim(),
    );
  }

  final String action;
  final int afterSeconds;
  final String disruptionLevel;

  /// 云侧是否下发了明确的恢复动作。未下发时端侧回退到基于 nature 的防御派生。
  bool get isPresent => action.isNotEmpty;

  Map<String, dynamic> toJson() {
    return <String, dynamic>{
      'action': action,
      'afterSeconds': afterSeconds,
      'disruptionLevel': disruptionLevel,
    };
  }
}
