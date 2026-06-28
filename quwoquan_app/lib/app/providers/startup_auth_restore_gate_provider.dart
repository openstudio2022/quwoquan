import 'package:flutter_riverpod/flutter_riverpod.dart';

/// 欢迎页可见前禁止 [AuthSessionController] 触发 store 读取。
final startupAuthRestoreGateProvider =
    NotifierProvider<StartupAuthRestoreGateNotifier, bool>(
      StartupAuthRestoreGateNotifier.new,
    );

class StartupAuthRestoreGateNotifier extends Notifier<bool> {
  @override
  bool build() => false;

  void open() {
    if (state) {
      return;
    }
    state = true;
  }
}
