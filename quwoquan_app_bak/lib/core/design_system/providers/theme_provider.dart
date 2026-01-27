import 'package:flutter_riverpod/flutter_riverpod.dart';

class ThemeState {
  final bool isDark;
  
  const ThemeState({this.isDark = false});
  
  ThemeState copyWith({bool? isDark}) {
    return ThemeState(isDark: isDark ?? this.isDark);
  }
}

class ThemeNotifier extends Notifier<ThemeState> {
  @override
  ThemeState build() {
    return const ThemeState();
  }
  
  void toggleTheme() {
    state = state.copyWith(isDark: !state.isDark);
  }
  
  void setDark(bool isDark) {
    state = state.copyWith(isDark: isDark);
  }
}

final themeProvider = NotifierProvider<ThemeNotifier, ThemeState>(() {
  return ThemeNotifier();
});

final effectiveIsDarkProvider = Provider<bool>((ref) {
  return ref.watch(themeProvider).isDark;
});

