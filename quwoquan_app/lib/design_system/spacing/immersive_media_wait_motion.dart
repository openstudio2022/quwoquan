/// 沉浸媒体等待滞回节奏 token（works-immersive-viewer REQ-020 唯一取值处）。
///
/// 三层滞回机制消除「系统响应恰卡在阈值附近导致指示闪现」：
/// 1. 延迟出现——阈值内零指示零动效；
/// 2. 最短展示——指示一旦出现必须保持满窗口再转场；
/// 3. 全程交叉淡出——任何状态间转换无硬切。
///
/// 3 秒慢提示与 6 秒终态不在此定义，复用
/// `runtime/shell/loading/app_request_wait_controller.dart` 的
/// `AppRequestWaitTimings`（全站唯一时间真相源）。
abstract final class ImmersiveMediaWaitMotion {
  /// 图片等待指示延迟出现阈值。
  ///
  /// 图片 CDN 响应 p50 约 300–600ms，取 500ms（iOS 系统惯例约 0.5s）让
  /// 大多数正常加载全程无指示；深底占位 + 跟手翻页本身即是即时响应反馈。
  /// 视频（REQ-013）保持 300ms：播放器初始化几乎必然超过该值，
  /// 不落在其响应分布中段，无闪现风险。
  static const Duration imageIndicatorDelay = Duration(milliseconds: 500);

  /// 指示最短展示窗口：出现后即使媒体随后就绪也保持满本时长再转场，
  /// 与延迟阈值构成滞回区间，任何完成时刻均不产生指示闪现。
  static const Duration indicatorMinDisplay = Duration(milliseconds: 400);

  /// 指示淡入时长（登场渐进，边界时刻不突兀）。
  static const Duration indicatorFadeIn = Duration(milliseconds: 200);

  /// 指示与内容/失败面之间的交叉淡出时长。
  static const Duration crossFade = Duration(milliseconds: 250);

  /// 延迟阈值内完成时内容的快速淡入：感知为瞬时且避免硬切闪帧。
  static const Duration quickReveal = Duration(milliseconds: 120);

  /// Reduce Motion 下所有转场的统一上限（滞回时长本身不变）。
  static const Duration reducedMotionTransition = Duration(milliseconds: 120);

  static Duration remainingIndicatorDisplay(DateTime shownAt, {DateTime? now}) {
    final remaining =
        indicatorMinDisplay - (now ?? DateTime.now()).difference(shownAt);
    return remaining <= Duration.zero ? Duration.zero : remaining;
  }
}
