/// HomepageStatusReport 页面提交动作的对象级观测端口。
///
/// presentation 只声明业务动作与结果；具体 telemetry catalog、错误码映射和
/// reporter 装配由 adapter/runtime composition 负责。
abstract interface class HomepageStatusReportActionTracker {
  Future<void> trackSubmit({
    required String homepageId,
    required bool succeeded,
    required DateTime startedAt,
    Object? error,
  });
}
