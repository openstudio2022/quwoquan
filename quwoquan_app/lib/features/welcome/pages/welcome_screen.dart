import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 欢迎页
///
/// 与 Figma 原型及趣我圈2026 WelcomeScreen 视觉、动效一致。
/// 动效顺序：水滴出现(100ms) -> 花瓣绽放(800ms) -> 文案出现(2000ms)
class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({
    super.key,
    required this.onFinish,
  });

  final VoidCallback onFinish;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen>
    with TickerProviderStateMixin {
  late AnimationController _stepController;
  late AnimationController _dropController;
  late List<AnimationController> _petalControllers;
  late AnimationController _textController;
  late AnimationController _buttonController;

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

  @override
  void initState() {
    super.initState();
    _dropController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _petalControllers = List.generate(
      8,
      (i) => AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 800),
      ),
    );
    _textController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _buttonController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _stepController = AnimationController(
      vsync: this,
      duration: Duration.zero,
    );

    Future<void> runSequence() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      if (!mounted) return;
      await _dropController.forward();
      await Future<void>.delayed(const Duration(milliseconds: 500));
      if (!mounted) return;
      for (var i = 0; i < 8; i++) {
        _petalControllers[i].forward();
        await Future<void>.delayed(const Duration(milliseconds: 40));
      }
      await Future<void>.delayed(const Duration(milliseconds: 800));
      if (!mounted) return;
      await _textController.forward();
      await Future<void>.delayed(const Duration(milliseconds: 1200));
      if (!mounted) return;
      await _buttonController.forward();
    }

    runSequence();
  }

  @override
  void dispose() {
    _dropController.dispose();
    for (final c in _petalControllers) {
      c.dispose();
    }
    _textController.dispose();
    _buttonController.dispose();
    _stepController.dispose();
    super.dispose();
  }

  void _handleRestart() {
    _dropController.reset();
    for (final c in _petalControllers) {
      c.reset();
    }
    _textController.reset();
    _buttonController.reset();
    setState(() {});
    Future<void>.delayed(const Duration(milliseconds: 100), () {
      if (!mounted) return;
      _dropController.forward();
      Future<void>.delayed(const Duration(milliseconds: 500), () {
        if (!mounted) return;
        for (var i = 0; i < 8; i++) {
          _petalControllers[i].forward();
        }
        Future<void>.delayed(const Duration(milliseconds: 800), () async {
          if (!mounted) return;
          await _textController.forward();
          await Future<void>.delayed(const Duration(milliseconds: 1200));
          if (!mounted) return;
          await _buttonController.forward();
        });
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.welcomeBackground,
      child: Stack(
        children: [
          _buildBackground(),
          _buildRestartButton(),
          _buildMainContent(),
          _buildBottomButton(),
          _buildFooter(),
        ],
      ),
    );
  }

  Widget _buildBackground() {
    return Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              AppColors.welcomeGradientStart,
              AppColors.welcomeBackground,
              AppColors.welcomeGradientEnd,
            ],
          ),
        ),
        child: Stack(
          children: [
            Positioned(
              top: -MediaQuery.of(context).size.height * 0.2,
              left: -MediaQuery.of(context).size.width * 0.2,
              child: Container(
                width: MediaQuery.of(context).size.width * 0.8,
                height: MediaQuery.of(context).size.width * 0.8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha:0.05),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha:0.1),
                      blurRadius: 120,
                      spreadRadius: 0,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRestartButton() {
    return Positioned(
      top: MediaQuery.of(context).padding.top + AppSpacing.lg,
      right: AppSpacing.lg,
      child: Material(
        color: AppColors.welcomeButtonBg,
        borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
        child: InkWell(
          onTap: _handleRestart,
          borderRadius: BorderRadius.circular(AppSpacing.fullBorderRadius),
          child: Padding(
            padding: EdgeInsets.all(AppSpacing.sm),
            child: Icon(
              Icons.refresh,
              size: AppSpacing.iconMedium,
              color: AppColors.welcomeForeground.withValues(alpha:0.5),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMainContent() {
    final topOffset = MediaQuery.of(context).size.height * 0.05;
    return Center(
      child: Transform.translate(
        offset: Offset(0, -topOffset),
        child: Padding(
          padding: EdgeInsets.only(
            left: AppSpacing.lg,
            right: AppSpacing.lg,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildGraphicArea(),
              SizedBox(height: AppSpacing.xl * 2.5),
              _buildTypography(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildGraphicArea() {
    const size = 256.0;
    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        children: [
          for (var i = 0; i < 8; i++) _buildPetal(i, size),
          _buildWaterDrop(size),
        ],
      ),
    );
  }

  Widget _buildPetal(int index, double parentSize) {
    return AnimatedBuilder(
      animation: _petalControllers[index],
      builder: (context, child) {
        final t = Curves.easeOutCubic.transform(_petalControllers[index].value);
        final opacity = t * 0.9;
        final scale = t;
        final rotation = _petalRotations[index] * math.pi / 180;
        return Transform.rotate(
          angle: rotation,
          child: Transform.scale(
            scale: scale,
            child: Opacity(
              opacity: opacity,
              child: child,
            ),
          ),
        );
      },
      child: SizedBox(
        width: parentSize,
        height: parentSize,
        child: Center(
          child: Transform.translate(
            offset: const Offset(0, -0.5 * 96),
            child: Container(
              width: 56,
              height: 96,
              decoration: BoxDecoration(
                color: _petalColors[index],
                borderRadius: BorderRadius.circular(30),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha:0.2),
                    blurRadius: 8,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildWaterDrop(double parentSize) {
    return AnimatedBuilder(
      animation: _dropController,
      builder: (context, child) {
        final t = Curves.easeOut.transform(_dropController.value);
        return Opacity(
          opacity: t,
          child: Transform.scale(
            scale: t,
            child: child,
          ),
        );
      },
      child: Container(
        width: 112,
        height: 112,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          gradient: RadialGradient(
            center: const Alignment(0.5, 0.4),
            colors: [
              Colors.white.withValues(alpha:0.4),
              Colors.white.withValues(alpha:0.1),
              Colors.white.withValues(alpha:0.02),
            ],
            stops: const [0.0, 0.5, 1.0],
          ),
          border: Border.all(
            color: Colors.white.withValues(alpha:0.1),
            width: 1,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.white.withValues(alpha:0.2),
              blurRadius: 20,
              spreadRadius: 0,
            ),
            BoxShadow(
              color: Colors.black.withValues(alpha:0.1),
              blurRadius: 40,
              offset: const Offset(0, 10),
            ),
          ],
        ),
        child: Stack(
          children: [
            Positioned(
              top: 0.25 * 112 - 8,
              left: 0.5 * 112 - 16,
              child: Container(
                width: 32,
                height: 16,
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha:0.6),
                  borderRadius: BorderRadius.circular(50),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.white.withValues(alpha:0.3),
                      blurRadius: 4,
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTypography() {
    return AnimatedBuilder(
      animation: _textController,
      builder: (context, child) {
        final t = Curves.easeOut.transform(_textController.value);
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, 20 * (1 - t)),
            child: child,
          ),
        );
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          ShaderMask(
            shaderCallback: (bounds) => LinearGradient(
              colors: [
                AppColors.welcomeForeground,
                AppColors.welcomeTitleGradientMid,
                AppColors.welcomeTitleGradientEnd,
              ],
            ).createShader(bounds),
            child: Text(
              UITextConstants.welcomeTitle,
              style: TextStyle(
                fontSize: AppTypography.welcomeHeroTitle,
                fontWeight: AppTypography.black,
                color: Colors.white,
                letterSpacing: -0.5,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.md),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Flexible(
                child: Text(
                  UITextConstants.welcomeMainSlogan,
                  style: TextStyle(
                    fontSize: AppTypography.xl,
                    fontWeight: AppTypography.medium,
                    color: AppColors.welcomeForegroundMuted,
                    letterSpacing: 1.0,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupXs),
              Icon(
                Icons.auto_awesome,
                size: AppSpacing.iconSmall,
                color: AppColors.welcomeForeground.withValues(alpha: 0.9),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// 欢迎页底部署名：居中、小字号、弱对比，与主按钮分离
  Widget _buildFooter() {
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.only(
            bottom: AppSpacing.md + MediaQuery.of(context).padding.bottom,
          ),
          child: AnimatedBuilder(
            animation: _textController,
            builder: (context, child) {
              return Opacity(
                opacity: Curves.easeOut.transform(_textController.value),
                child: child,
              );
            },
            child: Center(
              child: Text(
                UITextConstants.welcomeFooterCredit,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.medium,
                  color: AppColors.welcomeForegroundMuted.withValues(alpha: 0.8),
                  letterSpacing: 0.5,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// 底部按钮：Positioned 须为 Stack 直接子组件，不能包在 Opacity/AnimatedBuilder 内
  Widget _buildBottomButton() {
    return Positioned(
      bottom: MediaQuery.of(context).size.height * 0.1 +
          MediaQuery.of(context).padding.bottom,
      left: 0,
      right: 0,
      child: AnimatedBuilder(
        animation: _buttonController,
        builder: (context, child) {
          return Opacity(
            opacity: Curves.easeOut.transform(_buttonController.value),
            child: Center(
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  onTap: widget.onFinish,
                  borderRadius:
                      BorderRadius.circular(AppSpacing.fullBorderRadius),
                  child: Container(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.xl * 2,
                      vertical: AppSpacing.md,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.welcomeButtonBg,
                      border: Border.all(
                        color: AppColors.welcomeButtonBorder,
                        width: 1,
                      ),
                      borderRadius:
                          BorderRadius.circular(AppSpacing.fullBorderRadius),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          UITextConstants.welcomeButtonLabel,
                          style: TextStyle(
                            color: AppColors.welcomeForeground,
                            fontWeight: AppTypography.bold,
                            fontSize: AppTypography.lg,
                          ),
                        ),
                        SizedBox(width: AppSpacing.sm),
                        Icon(
                          Icons.arrow_forward,
                          size: AppSpacing.iconSmall,
                          color: AppColors.welcomeForeground,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
