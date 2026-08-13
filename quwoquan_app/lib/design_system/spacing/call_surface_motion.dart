/// 通话页动效时序 token：控制条自动隐藏、表面过渡与来电脉冲节奏的单一来源。
///
/// 通话页跨语音/视频/PiP/参与者格共用同一批时序；页面内禁止再写第二套
/// Duration 字面量，避免同类交互出现不一致的节奏。
abstract final class CallSurfaceMotion {
  /// 视频通话控制条无操作自动隐藏（画面优先，短驻留）。
  static const Duration videoControlsAutoHide = Duration(seconds: 3);

  /// 语音通话控制条无操作自动隐藏（无画面遮挡诉求，驻留更长）。
  static const Duration voiceControlsAutoHide = Duration(seconds: 5);

  /// 控制条/浮层显隐与 PiP 尺寸过渡。
  static const Duration surfaceTransition = Duration(milliseconds: 250);

  /// 参与者瓦片/质量指示等状态淡入淡出。
  static const Duration stateFade = Duration(milliseconds: 300);

  /// 来电头像脉冲一轮周期。
  static const Duration avatarPulseCycle = Duration(milliseconds: 2400);

  /// 来电头像多圈脉冲的相位错开间隔。
  static const Duration avatarPulseStagger = Duration(milliseconds: 600);
}
