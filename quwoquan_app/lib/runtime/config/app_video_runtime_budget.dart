/// App 视频运行时的唯一资源预算。
///
/// 播放器准入、typed 资源观测与候选证据必须读取同一常量，禁止各自复制
/// controller/decoder 槽位阈值。
/// 该预算属于跨页面 runtime config，不承载媒体业务对象事实。
abstract final class AppVideoRuntimeBudget {
  static const int maxConcurrentControllers = 2;
}
