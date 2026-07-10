import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter/widgets.dart';

enum AppFontSizePreset {
  xs(0.9),
  sm(0.95),
  md(1.0),
  lg(1.1),
  xl(1.2);

  const AppFontSizePreset(this.multiplier);

  final double multiplier;
}

class AccessibilityState {
  final double textScaleFactor;
  final AppFontSizePreset fontSizePreset;
  final bool boldText;
  final bool highContrast;
  final bool disableAnimations;

  const AccessibilityState({
    this.textScaleFactor = 1.0,
    this.fontSizePreset = AppFontSizePreset.md,
    this.boldText = false,
    this.highContrast = false,
    this.disableAnimations = false,
  });

  double get actualTextScaleFactor =>
      (textScaleFactor * fontSizePreset.multiplier).clamp(0.85, 1.6).toDouble();

  AccessibilityState copyWith({
    double? textScaleFactor,
    AppFontSizePreset? fontSizePreset,
    bool? boldText,
    bool? highContrast,
    bool? disableAnimations,
  }) {
    return AccessibilityState(
      textScaleFactor: textScaleFactor ?? this.textScaleFactor,
      fontSizePreset: fontSizePreset ?? this.fontSizePreset,
      boldText: boldText ?? this.boldText,
      highContrast: highContrast ?? this.highContrast,
      disableAnimations: disableAnimations ?? this.disableAnimations,
    );
  }

  @override
  bool operator ==(Object other) {
    return other is AccessibilityState &&
        other.textScaleFactor == textScaleFactor &&
        other.fontSizePreset == fontSizePreset &&
        other.boldText == boldText &&
        other.highContrast == highContrast &&
        other.disableAnimations == disableAnimations;
  }

  @override
  int get hashCode => Object.hash(
    textScaleFactor,
    fontSizePreset,
    boldText,
    highContrast,
    disableAnimations,
  );
}

class AccessibilityNotifier extends Notifier<AccessibilityState> {
  @override
  AccessibilityState build() {
    return const AccessibilityState();
  }

  void setSystemTextScaleFactor(double value) {
    final normalized = value <= 0 ? 1.0 : value;
    if (state.textScaleFactor == normalized) return;
    state = state.copyWith(textScaleFactor: normalized);
  }

  void setTextScaleFactor(double value) {
    setSystemTextScaleFactor(value);
  }

  void setFontSizePreset(AppFontSizePreset preset) {
    if (state.fontSizePreset == preset) return;
    state = state.copyWith(fontSizePreset: preset);
  }

  void setBoldText(bool enabled) {
    if (state.boldText == enabled) return;
    state = state.copyWith(boldText: enabled);
  }

  void setHighContrast(bool enabled) {
    if (state.highContrast == enabled) return;
    state = state.copyWith(highContrast: enabled);
  }

  void updateFromMediaQueryData(MediaQueryData data) {
    final next = state.copyWith(
      textScaleFactor: data.textScaler.scale(1.0),
      boldText: data.boldText,
      highContrast: data.highContrast,
      disableAnimations: data.disableAnimations,
    );
    if (next == state) return;
    state = next;
  }
}

final accessibilityProvider =
    NotifierProvider<AccessibilityNotifier, AccessibilityState>(() {
      return AccessibilityNotifier();
    });
