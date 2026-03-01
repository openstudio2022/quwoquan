import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'package:quwoquan_app/components/assistant/petal_mark.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum AssistantCenterVisualState {
  silent,
  wake,
  listening,
}

class BottomNavigationWidget extends ConsumerStatefulWidget {
  final int currentIndex;
  final Function(int) onTap;
  final AssistantCenterVisualState assistantVisualState;

  const BottomNavigationWidget({
    super.key,
    required this.currentIndex,
    required this.onTap,
    required this.assistantVisualState,
  });

  @override
  ConsumerState<BottomNavigationWidget> createState() =>
      _BottomNavigationWidgetState();
}

class _BottomNavigationWidgetState extends ConsumerState<BottomNavigationWidget>
    with TickerProviderStateMixin {
  late final AnimationController _listeningPulseController;
  late final Animation<double> _listeningPulse;
  late final List<AnimationController> _bloomControllers;

  @override
  void initState() {
    super.initState();
    _listeningPulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _listeningPulse = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(
      CurvedAnimation(
        parent: _listeningPulseController,
        curve: Curves.easeInOut,
      ),
    );
    _bloomControllers = List.generate(
      8,
      (i) => AnimationController(
        vsync: this,
        duration: const Duration(milliseconds: 800),
      ),
    );
    _syncListeningAnimation(widget.assistantVisualState);
    _runBloomSequence();
  }

  Future<void> _runBloomSequence() async {
    await Future<void>.delayed(const Duration(milliseconds: 50));
    if (!mounted) return;
    for (var i = 0; i < 8; i++) {
      unawaited(_bloomControllers[i].forward());
      await Future<void>.delayed(const Duration(milliseconds: 40));
    }
  }

  @override
  void didUpdateWidget(covariant BottomNavigationWidget oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.assistantVisualState != widget.assistantVisualState) {
      _syncListeningAnimation(widget.assistantVisualState);
    }
  }

  void _syncListeningAnimation(AssistantCenterVisualState state) {
    if (state == AssistantCenterVisualState.listening) {
      _listeningPulseController.repeat(reverse: true);
      return;
    }
    _listeningPulseController.stop();
    _listeningPulseController.value = 0;
  }

  @override
  void dispose() {
    _listeningPulseController.dispose();
    for (final c in _bloomControllers) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final themeDark = ref.watch(isDarkProvider);
    final forceDark = ref.watch(videoForceDarkProvider).forceDark;
    final isDark = themeDark || forceDark;
    final navBackground = forceDark
        ? AppColors.worksBackground
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

    final items = [
      {'label': AppConceptConstants.discovery, 'isCenter': false},
      {'label': AppConceptConstants.circles, 'isCenter': false},
      {'label': AppConceptConstants.assistantLabel, 'isCenter': true},
      {'label': AppConceptConstants.chat, 'isCenter': false},
      {'label': AppConceptConstants.profile, 'isCenter': false},
    ];

    return Container(
      height: AppSpacing.bottomNavHeight,
      decoration: BoxDecoration(
        color: navBackground,
      ),
      child: Row(
        children: items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final isSelected = index == widget.currentIndex;
          final isCenter = item['isCenter'] as bool;

          return Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => widget.onTap(index),
              child: Container(
                alignment: Alignment.center,
                padding: EdgeInsets.symmetric(
                  horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                  vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                ),
                constraints: BoxConstraints(
                  minHeight: AppSpacing.minInteractiveSize,
                ),
                child: isCenter
                    ? _buildCenterIcon(
                        isSelected: isSelected,
                        isDark: isDark,
                        visualState: widget.assistantVisualState,
                      )
                    : _buildTextLabel(
                        label: item['label'] as String,
                        isSelected: isSelected,
                        isDark: isDark,
                      ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildTextLabel({
    required String label,
    required bool isSelected,
    required bool isDark,
  }) {
    final color = isSelected
        ? (isDark
            ? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)
            : Colors.black)
        : AppColorsFunctional.getColor(isDark, ColorType.tabUnselected);
    return Center(
      child: Text(
        label,
        style: TextStyle(
          fontSize: (isSelected
                  ? AppTypography.bottomNavLabelSelected
                  : AppTypography.bottomNavLabelUnselected),
          fontWeight: AppTypography.bottomNavLabelWeight,
          color: color,
        ),
      ),
    );
  }

  Widget _buildCenterIcon({
    required bool isSelected,
    required bool isDark,
    required AssistantCenterVisualState visualState,
  }) {
    final isWake = visualState == AssistantCenterVisualState.wake;
    final isListening = visualState == AssistantCenterVisualState.listening;
    final currentScale = isWake ? 1.06 : (isListening ? 1.02 : 1.0);

    return Center(
      child: AnimatedBuilder(
        animation: Listenable.merge([_listeningPulse, ..._bloomControllers]),
        builder: (context, child) {
          final bloomValues = _bloomControllers
              .map(
                (c) => Curves.easeOutCubic.transform(c.value),
              )
              .toList();
          final pulse = Curves.easeInOut.transform(_listeningPulse.value);
          final maxPetalOpacity = isWake
              ? 1.0
              : (isListening ? (0.95 + pulse * 0.05) : 0.95);
          return AnimatedScale(
            scale: currentScale,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOutCubic,
            child: PetalMark(
              size: (AppSpacing.minInteractiveSize * 0.92).sp,
              isDarkMode: isDark,
              bloomValues: bloomValues,
              maxPetalOpacity: maxPetalOpacity,
            ),
          );
        },
      ),
    );
  }
}