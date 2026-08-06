/// 安全 Shell 在 HTTPS trust 与认证前置门通过后才能触发的业务预热边界。
///
/// runtime 只拥有调度时机，不知道具体内容队列或领域 Provider；生产
/// adapter 只能在 `runtime/di/**` 组装。
abstract interface class StartupContentWarmupPort {
  void warmUp();
}
