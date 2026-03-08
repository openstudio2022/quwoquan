import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// Pulsating avatar animation for outgoing/incoming call screens.
/// Shows 3 concentric rings expanding and fading around a center avatar.
class CallerAvatarPulse extends StatefulWidget {
  const CallerAvatarPulse({
    super.key,
    required this.displayName,
    this.avatarUrl,
    this.size,
  });

  final String displayName;
  final String? avatarUrl;
  final double? size;

  @override
  State<CallerAvatarPulse> createState() => _CallerAvatarPulseState();
}

class _CallerAvatarPulseState extends State<CallerAvatarPulse>
    with TickerProviderStateMixin {
  late final List<AnimationController> _controllers;
  late final List<Animation<double>> _scaleAnimations;
  late final List<Animation<double>> _opacityAnimations;

  static const _ringCount = 3;
  static const _duration = Duration(milliseconds: 2400);
  static const _staggerDelay = Duration(milliseconds: 600);

  @override
  void initState() {
    super.initState();
    _controllers = List.generate(_ringCount, (i) {
      return AnimationController(
        vsync: this,
        duration: _duration,
      );
    });

    _scaleAnimations = _controllers.map((c) {
      return Tween<double>(begin: 1.0, end: 2.2).animate(
        CurvedAnimation(parent: c, curve: Curves.easeOut),
      );
    }).toList();

    _opacityAnimations = _controllers.map((c) {
      return Tween<double>(begin: 0.6, end: 0.0).animate(
        CurvedAnimation(parent: c, curve: Curves.easeOut),
      );
    }).toList();

    for (var i = 0; i < _ringCount; i++) {
      Future.delayed(_staggerDelay * i, () {
        if (mounted) {
          _controllers[i].repeat();
        }
      });
    }
  }

  @override
  void dispose() {
    for (final c in _controllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final avatarRadius = (widget.size ?? AppSpacing.oneHundred) / 2;

    return SizedBox(
      width: avatarRadius * 4.4,
      height: avatarRadius * 4.4,
      child: Stack(
        alignment: Alignment.center,
        children: [
          for (var i = 0; i < _ringCount; i++)
            AnimatedBuilder(
              animation: _controllers[i],
              builder: (context, child) {
                return Transform.scale(
                  scale: _scaleAnimations[i].value,
                  child: Container(
                    width: avatarRadius * 2,
                    height: avatarRadius * 2,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(
                        color: AppColors.white
                            .withValues(alpha: _opacityAnimations[i].value),
                        width: AppSpacing.oneHalf,
                      ),
                    ),
                  ),
                );
              },
            ),
          CircleAvatar(
            radius: avatarRadius,
            backgroundColor: AppColors.primaryColor.withValues(alpha: 0.4),
            backgroundImage: widget.avatarUrl != null
                ? NetworkImage(widget.avatarUrl!)
                : null,
            child: widget.avatarUrl == null
                ? Text(
                    widget.displayName.isNotEmpty
                        ? widget.displayName[0].toUpperCase()
                        : '?',
                    style: TextStyle(
                      color: AppColors.white,
                      fontSize: AppTypography.xxxl,
                      fontWeight: AppTypography.semiBold,
                    ),
                  )
                : null,
          ),
        ],
      ),
    );
  }
}
