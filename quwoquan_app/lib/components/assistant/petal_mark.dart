import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 小趣花瓣标识（与欢迎页像素级一致）
///
/// 8 片彩色花瓣环绕，比例与 [WelcomeScreen] 完全一致，仅按 [size] 等比缩放。
/// [bloomValues] 为 8 个 0~1 的绽放进度，用于绽放动效；为 null 时视为全部已绽开。
class PetalMark extends StatelessWidget {
  const PetalMark({
    super.key,
    required this.size,
    required this.isDarkMode,
    this.bloomValues,
    this.maxPetalOpacity = 0.9,
    this.showCenterCore = true,
    this.centerCoreScale = 0.18,
    this.centerCoreBorderAlphaLight = 0.10,
    this.centerCoreBorderAlphaDark = 0.18,
  });

  final double size;
  final bool isDarkMode;
  final List<double>? bloomValues;
  final double maxPetalOpacity;
  final bool showCenterCore;
  final double centerCoreScale;
  final double centerCoreBorderAlphaLight;
  final double centerCoreBorderAlphaDark;

  /// 欢迎页基准尺寸（像素级一致来源）
  static const double _welcomeBaseSize = 256.0;

  /// 欢迎页单瓣尺寸
  static const double _welcomePetalWidth = 56.0;
  static const double _welcomePetalHeight = 96.0;
  static const double _welcomePetalOffset = 48.0;
  static const double _welcomePetalBorderRadius = 30.0;
  static const double _welcomeShadowBlur = 8.0;
  static const Offset _welcomeShadowOffset = Offset(0, 4);

  static const List<Color> _petalColors = [
    AppColors.welcomePetalOrange,
    AppColors.welcomePetalYellow,
    AppColors.welcomePetalLime,
    AppColors.welcomePetalEmerald,
    AppColors.welcomePetalCyan,
    AppColors.welcomePetalSky,
    AppColors.welcomePetalPurple,
    AppColors.welcomePetalRose,
  ];

  static const List<double> _petalRotations = [
    0, 45, 90, 135, 180, 225, 270, 315,
  ];

  double get _scale => size / _welcomeBaseSize;

  double get _petalWidth => _welcomePetalWidth * _scale;

  double get _petalHeight => _welcomePetalHeight * _scale;

  double get _petalOffset => _welcomePetalOffset * _scale;

  double get _petalBorderRadius => _welcomePetalBorderRadius * _scale;

  double get _shadowBlur => _welcomeShadowBlur * _scale;

  Offset get _shadowOffset => Offset(
        _welcomeShadowOffset.dx * _scale,
        _welcomeShadowOffset.dy * _scale,
      );

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          for (var i = 0; i < 8; i++) _buildPetal(i),
          if (showCenterCore) _buildCenterCore(),
        ],
      ),
    );
  }

  Widget _buildPetal(int index) {
    final t = bloomValues != null && index < bloomValues!.length
        ? bloomValues![index].clamp(0.0, 1.0)
        : 1.0;
    final opacity = t * maxPetalOpacity;
    final scale = t;
    final rotation = _petalRotations[index] * math.pi / 180;

    return Transform.rotate(
      angle: rotation,
      child: Transform.scale(
        scale: scale,
        alignment: Alignment.center,
        child: Opacity(
          opacity: opacity,
          child: SizedBox(
            width: size,
            height: size,
            child: Center(
              child: Transform.translate(
                offset: Offset(0, -_petalOffset),
                child: Container(
                  width: _petalWidth,
                  height: _petalHeight,
                  decoration: BoxDecoration(
                    color: _petalColors[index],
                    borderRadius: BorderRadius.circular(_petalBorderRadius),
                    boxShadow: [
                      BoxShadow(
                        color: AppColors.black.withValues(
                          alpha: isDarkMode ? 0.26 : 0.2,
                        ),
                        blurRadius: _shadowBlur,
                        offset: _shadowOffset,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCenterCore() {
    final coreSize = size * centerCoreScale;
    final coreBorderWidth = (_scale * 1.6).clamp(0.6, 1.2);
    final borderColor = isDarkMode
        ? AppColors.white.withValues(alpha: centerCoreBorderAlphaDark)
        : AppColors.black.withValues(alpha: centerCoreBorderAlphaLight);
    return Container(
      width: coreSize,
      height: coreSize,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        gradient: RadialGradient(
          center: const Alignment(-0.15, -0.15),
          colors: [
            AppColors.white,
            AppColors.white.withValues(alpha: 0.94),
            AppColors.white.withValues(alpha: 0.78),
          ],
          stops: const [0.0, 0.65, 1.0],
        ),
        border: Border.all(
          color: borderColor,
          width: coreBorderWidth,
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDarkMode ? 0.16 : 0.08),
            blurRadius: (_scale * 6).clamp(1.2, 2.6),
            offset: Offset(0, (_scale * 2).clamp(0.4, 1.0)),
          ),
        ],
      ),
    );
  }
}
