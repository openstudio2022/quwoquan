import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/app/app_startup_runtime.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/welcome/welcome_appearance.dart';
import 'package:quwoquan_app/ui/welcome/widgets/welcome_flower_mark.dart';

enum WelcomeStartupStageStatus { pending, running, complete, failed }

class WelcomeStartupStageState {
  const WelcomeStartupStageState({required this.label, required this.status});

  final String label;
  final WelcomeStartupStageStatus status;
}

class WelcomeStartupLoadingState {
  const WelcomeStartupLoadingState({
    required this.title,
    required this.subtitle,
    this.hint,
    this.stages = const <WelcomeStartupStageState>[],
    this.actionLabel,
    this.onAction,
    this.isError = false,
  });

  final String title;
  final String subtitle;
  final String? hint;
  final List<WelcomeStartupStageState> stages;
  final String? actionLabel;
  final FutureOr<void> Function()? onAction;
  final bool isError;
}

/// 欢迎页
///
/// 与 Figma 原型及趣我圈2026 WelcomeScreen 视觉、动效一致。
/// 动效顺序：品牌内容首帧可见 -> 花瓣/文案微动效增强 -> 直接进入首页。
class WelcomeScreen extends StatefulWidget {
  const WelcomeScreen({
    super.key,
    required this.onFinish,
    this.deferSequenceStart = false,
    this.onSequenceComplete,
    this.onWelcomeVisible,
    this.startupLoading,
  });

  final VoidCallback onFinish;
  final bool deferSequenceStart;
  final VoidCallback? onSequenceComplete;
  final VoidCallback? onWelcomeVisible;
  final WelcomeStartupLoadingState? startupLoading;

  @override
  State<WelcomeScreen> createState() => _WelcomeScreenState();
}

class _WelcomeScreenState extends State<WelcomeScreen>
    with TickerProviderStateMixin {
  static Duration get _minimumSequenceDuration => kReleaseMode
      ? const Duration(milliseconds: 1500)
      : const Duration(milliseconds: 200);
  static const Duration _petalDuration = Duration(milliseconds: 700);
  static const Duration _petalStagger = Duration(milliseconds: 70);
  static const Duration _postBloomPause = Duration(milliseconds: 180);
  static const Duration _textDuration = Duration(milliseconds: 760);
  static const Duration _finalPause = Duration(milliseconds: 120);
  static const Duration _firstFrameRasterTimeout = Duration(milliseconds: 1500);
  static const Duration _visibleFrameGuard = Duration(milliseconds: 300);
  static const double _initialPetalProgress = 0.24;
  static const double _initialTextProgress = 1.0;
  static const int _petalCount = 8;

  static final List<double> _staticPetalProgresses = List<double>.filled(
    _petalCount,
    _initialPetalProgress,
  );

  List<AnimationController>? _petalControllers;
  AnimationController? _textController;
  final Set<Timer> _sequenceTimers = <Timer>{};
  bool _finishHandled = false;
  bool _sequenceCompletionDispatched = false;
  bool _sequenceStarted = false;
  bool _animationsReady = false;
  bool _brandedContentReady = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      AppStartupRuntime.instance.markWelcomeShown();
      if (!mounted) {
        return;
      }
      setState(() => _brandedContentReady = true);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _installAnimationControllers();
        scheduleMicrotask(() {
          if (!mounted) {
            return;
          }
          widget.onWelcomeVisible?.call();
        });
        unawaited(_beginAnimatedSequence());
      });
    });
  }

  void _installAnimationControllers() {
    if (_animationsReady) {
      return;
    }
    _petalControllers = List.generate(
      _petalCount,
      (i) => AnimationController(
        vsync: this,
        duration: _petalDuration,
        value: _initialPetalProgress,
      ),
    );
    _textController = AnimationController(
      vsync: this,
      duration: _textDuration,
      value: _initialTextProgress,
    );
    _animationsReady = true;
  }

  Future<void> _beginAnimatedSequence() async {
    if (_sequenceStarted) {
      return;
    }
    if (widget.deferSequenceStart) {
      if (kReleaseMode) {
        await WidgetsBinding.instance.endOfFrame;
        if (!mounted) {
          return;
        }
        await _waitForFirstFrameRasterizedOrTimeout();
        if (!mounted) {
          return;
        }
        await _waitForManagedDelay(_visibleFrameGuard);
        if (!mounted) {
          return;
        }
      } else {
        await _waitForManagedDelay(const Duration(milliseconds: 16));
        if (!mounted) {
          return;
        }
      }
    }
    if (!mounted || !_animationsReady) {
      return;
    }
    _sequenceStarted = true;
    _runSequence();
  }

  @override
  void dispose() {
    for (final timer in _sequenceTimers) {
      timer.cancel();
    }
    _sequenceTimers.clear();
    final petalControllers = _petalControllers;
    if (petalControllers != null) {
      for (final c in petalControllers) {
        c.dispose();
      }
    }
    _textController?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final appearance = WelcomeAppearance.of(context);
    if (!_brandedContentReady) {
      return ColoredBox(
        color: appearance.background,
        child: Center(
          child: WelcomeFlowerMark(
            appearance: appearance,
            petalProgresses: _staticPetalProgresses,
          ),
        ),
      );
    }
    return AppScaffold(
      backgroundColor: appearance.background,
      resizeToAvoidBottomInset: false,
      body: DefaultTextStyle.merge(
        style: const TextStyle(
          decoration: TextDecoration.none,
          decorationThickness: 0,
        ),
        child: Stack(
          fit: StackFit.expand,
          children: [
            _buildBackground(appearance),
            _buildMainContent(appearance),
            if (_shouldShowStartupLoading)
              _buildStartupInlineHint(appearance)
            else
              _buildAssistantWhisper(appearance),
          ],
        ),
      ),
    );
  }

  bool get _shouldShowStartupLoading => widget.startupLoading != null;

  Duration get _sequenceCompletionDuration {
    final lastPetalComplete =
        (_petalStagger * (_petalCount - 1)) + _petalDuration;
    final remainingText = Duration(
      microseconds: (_textDuration.inMicroseconds * (1 - _initialTextProgress))
          .round(),
    );
    final visualComplete =
        lastPetalComplete + _postBloomPause + remainingText + _finalPause;
    return visualComplete > _minimumSequenceDuration
        ? visualComplete
        : _minimumSequenceDuration;
  }

  Future<void> _waitForFirstFrameRasterizedOrTimeout() async {
    if (WidgetsBinding.instance.firstFrameRasterized) {
      return;
    }
    final timeout = Completer<void>();
    late final Timer timer;
    timer = Timer(_firstFrameRasterTimeout, () {
      _sequenceTimers.remove(timer);
      if (!timeout.isCompleted) {
        timeout.complete();
      }
    });
    _sequenceTimers.add(timer);
    await Future.any<void>([
      WidgetsBinding.instance.waitUntilFirstFrameRasterized,
      timeout.future,
    ]);
    if (_sequenceTimers.remove(timer)) {
      timer.cancel();
    }
  }

  Future<void> _waitForManagedDelay(Duration duration) {
    if (duration <= Duration.zero) {
      return Future<void>.value();
    }
    final completer = Completer<void>();
    late final Timer timer;
    timer = Timer(duration, () {
      _sequenceTimers.remove(timer);
      if (!completer.isCompleted) {
        completer.complete();
      }
    });
    _sequenceTimers.add(timer);
    return completer.future;
  }

  void _runSequence() {
    if (!mounted || !_animationsReady) {
      return;
    }
    final petalControllers = _petalControllers;
    if (petalControllers == null) {
      return;
    }
    if (mounted) {
      setState(() {});
    }
    for (var i = 0; i < _petalCount; i++) {
      final startDelay = _petalStagger * i;
      _schedule(startDelay, () {
        if (mounted && petalControllers[i].value < 1) {
          petalControllers[i].forward();
        }
      });
    }

    _schedule(_sequenceCompletionDuration, _dispatchSequenceCompletion);
  }

  Widget _buildBackground(WelcomeAppearance appearance) {
    return Positioned.fill(
      child: DecoratedBox(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              appearance.gradientStart,
              appearance.background,
              appearance.gradientEnd,
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
                  color: appearance.decorSoftBlobFill,
                  boxShadow: [
                    BoxShadow(
                      color: appearance.decorSoftBlobShadow,
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

  /// 主内容竖向分布：用 Spacer 2:3 让「花瓣 + 趣我圈 + slogan」自然形成一个
  /// 品牌视觉簇，重心略向上偏（符合启动页阅读习惯），上下与 SafeArea / 注脚的留白比例
  /// 由 Spacer 决定，不再硬性 `Transform.translate` 偏移。
  ///
  /// - 花瓣 → 「趣我圈」：40px（`xl + sm`），让图标与品牌标题成为同一组
  /// - 「趣我圈」 → 主 slogan：16px（`md`），形成更紧凑的品牌锁定组合
  Widget _buildMainContent(WelcomeAppearance appearance) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.lg),
        child: Column(
          children: [
            const Spacer(flex: 2),
            _buildGraphicArea(appearance),
            SizedBox(height: AppSpacing.xl + AppSpacing.sm),
            _buildTypography(appearance),
            const Spacer(flex: 3),
          ],
        ),
      ),
    );
  }

  Widget _buildGraphicArea(WelcomeAppearance appearance) {
    if (!_animationsReady) {
      return WelcomeFlowerMark(
        appearance: appearance,
        petalProgresses: _staticPetalProgresses,
      );
    }
    final petalControllers = _petalControllers!;
    return SizedBox(
      width: AppSpacing.welcomeGraphicDiameter,
      height: AppSpacing.welcomeGraphicDiameter,
      child: AnimatedBuilder(
        animation: Listenable.merge(petalControllers),
        builder: (context, child) {
          return WelcomeFlowerMark(
            appearance: appearance,
            petalProgresses: [
              for (final controller in petalControllers) controller.value,
            ],
          );
        },
      ),
    );
  }

  Widget _buildTypography(WelcomeAppearance appearance) {
    final content = Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        ShaderMask(
          shaderCallback: (bounds) => LinearGradient(
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
            stops: const [0.0, 0.48, 1.0],
            colors: [
              AppColors.welcomeTitleGradientEnd,
              AppColors.welcomeTitleGradientMid,
              AppColors.welcomeForeground,
            ],
          ).createShader(bounds),
          child: Text(
            UITextConstants.welcomeTitle,
            style: TextStyle(
              fontSize: AppTypography.welcomeHeroTitle,
              fontWeight: AppTypography.black,
              color: AppColors.white,
              letterSpacing: -0.5,
              decoration: TextDecoration.none,
            ),
          ),
        ),
        SizedBox(height: AppSpacing.md),
        Text(
          UITextConstants.welcomeMainSlogan,
          style: TextStyle(
            fontSize: AppTypography.xl,
            fontWeight: AppTypography.medium,
            color: appearance.foregroundMuted,
            letterSpacing: 1.0,
            decoration: TextDecoration.none,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
    if (!_animationsReady) {
      return content;
    }
    final textController = _textController!;
    return AnimatedBuilder(
      animation: textController,
      builder: (context, child) {
        final t = Curves.easeOut.transform(textController.value);
        return Opacity(
          opacity: t,
          child: Transform.translate(
            offset: Offset(0, 20 * (1 - t)),
            child: child,
          ),
        );
      },
      child: content,
    );
  }

  /// 欢迎页底部「小趣低声注脚」：单行、居中、极小字、弱对比。
  ///
  /// 上方已有「花瓣 + 趣我圈 + 主 slogan」三层信息饱和，这里只承担 AI Native
  /// 署名职责（让用户知道"是小趣在主动撮合"），形态克制为"版权署名级"微注脚：
  /// - 居中对齐，与上方版面节奏一致（消除左/中对齐割裂）
  /// - 单行紧凑：`✦ 小趣  专注你的热爱，剩下的交给我`
  /// - 字号 `AppTypography.xs`（10pt），透明度降至 0.7，避免与上方任何元素争视觉权重
  /// - sparkle 作为 WidgetSpan 内联，与文字 baseline 对齐
  ///
  /// 动效：`_textController` 后 75% 出现，让上方 slogan 先到位。
  Widget _buildAssistantWhisper(WelcomeAppearance appearance) {
    final textColor = appearance.foregroundMuted.withValues(alpha: 0.78);
    final whisper = Text.rich(
      TextSpan(
        style: TextStyle(
          fontSize: AppTypography.xs,
          fontWeight: AppTypography.regular,
          color: textColor,
          letterSpacing: 0.3,
          height: AppTypography.lineHeightCompact,
          decoration: TextDecoration.none,
        ),
        children: [
          WidgetSpan(
            alignment: PlaceholderAlignment.middle,
            child: Padding(
              padding: EdgeInsets.only(right: AppSpacing.xs),
              child: Icon(
                CupertinoIcons.sparkles,
                size: AppSpacing.fourteen,
                color: AppColors.assistantMarkColorOnDark,
              ),
            ),
          ),
          TextSpan(
            text: '${UITextConstants.assistantWhisperSignature}  ',
            style: TextStyle(
              fontWeight: AppTypography.semiBold,
              color: AppColors.welcomeForeground.withValues(
                alpha: 0.85,
              ),
            ),
          ),
          TextSpan(text: UITextConstants.assistantWhisperLine),
        ],
      ),
      textAlign: TextAlign.center,
    );
    final animatedWhisper = !_animationsReady
        ? whisper
        : Builder(
            builder: (context) {
              final delayed = CurvedAnimation(
                parent: _textController!,
                curve: const Interval(0.25, 1.0, curve: Curves.easeOut),
              );
              return AnimatedBuilder(
                animation: delayed,
                builder: (context, child) {
                  final t = delayed.value;
                  return Opacity(
                    opacity: t,
                    child: Transform.translate(
                      offset: Offset(0, 6 * (1 - t)),
                      child: child,
                    ),
                  );
                },
                child: whisper,
              );
            },
          );
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: EdgeInsets.only(
            left: AppSpacing.lg,
            right: AppSpacing.lg,
            bottom: AppSpacing.xl + MediaQuery.of(context).padding.bottom,
          ),
          child: animatedWhisper,
        ),
      ),
    );
  }

  Widget _buildStartupInlineHint(WelcomeAppearance appearance) {
    final loading = widget.startupLoading;
    if (loading == null) {
      return const SizedBox.shrink();
    }
    final hint = (loading.hint?.trim().isNotEmpty ?? false)
        ? loading.hint!.trim()
        : UITextConstants.startupStillStartingInline;
    return Positioned(
      left: AppSpacing.containerLg,
      right: AppSpacing.containerLg,
      bottom: AppSpacing.xl + MediaQuery.of(context).padding.bottom,
      child: SafeArea(
        top: false,
        child: Center(
          child: SizedBox(
            height: AppSpacing.radiusTwentyFour,
            child: Text(
              hint,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.xs,
                fontWeight: AppTypography.medium,
                color: appearance.foregroundMuted.withValues(alpha: 0.82),
                height: AppTypography.lineHeightCompact,
                decoration: TextDecoration.none,
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _finishWelcome() {
    if (_finishHandled) {
      return;
    }
    _finishHandled = true;
    widget.onFinish();
  }

  void _dispatchSequenceCompletion() {
    if (_sequenceCompletionDispatched) {
      return;
    }
    if (mounted) {
      setState(() => _sequenceCompletionDispatched = true);
    } else {
      _sequenceCompletionDispatched = true;
    }
    if (widget.onSequenceComplete != null) {
      widget.onSequenceComplete!.call();
      return;
    }
    _finishWelcome();
  }

  void _schedule(Duration duration, VoidCallback callback) {
    if (duration <= Duration.zero) {
      callback();
      return;
    }
    late final Timer timer;
    timer = Timer(duration, () {
      _sequenceTimers.remove(timer);
      callback();
    });
    _sequenceTimers.add(timer);
  }
}
