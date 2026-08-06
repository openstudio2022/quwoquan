import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/state/startup_auth_restore_gate_provider.dart';

void main() {
  test('startup auth restore gate is closed before welcome window opens', () {
    final container = ProviderContainer();
    addTearDown(container.dispose);
    expect(container.read(startupAuthRestoreGateProvider), isFalse);
    container.read(startupAuthRestoreGateProvider.notifier).open();
    expect(container.read(startupAuthRestoreGateProvider), isTrue);
  });
}
