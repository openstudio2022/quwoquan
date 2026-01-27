import 'package:flutter_riverpod/flutter_riverpod.dart';

class AccessibilityState {
  final double textScaleFactor;
  final bool boldText;
  final bool highContrast;
  
  const AccessibilityState({
    this.textScaleFactor = 1.0,
    this.boldText = false,
    this.highContrast = false,
  });
  
  AccessibilityState copyWith({
    double? textScaleFactor,
    bool? boldText,
    bool? highContrast,
  }) {
    return AccessibilityState(
      textScaleFactor: textScaleFactor ?? this.textScaleFactor,
      boldText: boldText ?? this.boldText,
      highContrast: highContrast ?? this.highContrast,
    );
  }
}

class AccessibilityNotifier extends Notifier<AccessibilityState> {
  @override
  AccessibilityState build() {
    return const AccessibilityState();
  }
}

final accessibilityProvider = NotifierProvider<AccessibilityNotifier, AccessibilityState>(() {
  return AccessibilityNotifier();
});

