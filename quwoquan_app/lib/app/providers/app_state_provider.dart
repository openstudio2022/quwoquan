import 'package:flutter_riverpod/flutter_riverpod.dart';

class AppState {
  final bool isInitialized;
  final String? error;
  
  const AppState({
    this.isInitialized = false,
    this.error,
  });
  
  AppState copyWith({bool? isInitialized, String? error}) {
    return AppState(
      isInitialized: isInitialized ?? this.isInitialized,
      error: error,
    );
  }
}

class AppStateNotifier extends Notifier<AppState> {
  @override
  AppState build() {
    return const AppState();
  }
  
  Future<void> initialize() async {
    state = const AppState(isInitialized: true);
  }
}

final appStateProvider = NotifierProvider<AppStateNotifier, AppState>(() {
  return AppStateNotifier();
});

// Removed duplicate lastMainTabBeforeAssistantProvider

