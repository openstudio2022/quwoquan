// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_state_machine.dart';

void main() {
  const trustedBaseUrls = <String>[
    'https://quwoquan.com',
    'https://cdn.quwoquan.com/download',
  ];

  test('startup version state can only be confirmed by a valid response', () {
    final machine = RecoveryStateMachine();
    expect(machine.snapshot.phase, RecoveryPhase.startupChecking);

    expect(machine.markVersionUnavailable(), isTrue);
    expect(machine.snapshot.phase, RecoveryPhase.startupVersionUnavailable);
    expect(
      machine.confirmVersion(
        currentBuild: 18100,
        latestBuild: 18201,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupUpdateRequired);

    expect(
      machine.confirmVersion(
        currentBuild: 18100,
        latestBuild: 18300,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
  });

  test(
    'runtime recovery can begin only once and failure moves to version check',
    () {
      final machine = RecoveryStateMachine(
        initial: const RecoverySnapshot(
          phase: RecoveryPhase.runtimeUnavailable,
        ),
      );
      expect(machine.beginRuntimeReentry(), isTrue);
      expect(machine.snapshot.phase, RecoveryPhase.runtimeReentering);
      expect(machine.beginRuntimeReentry(), isFalse);
      expect(machine.failRuntimeReentry(), isTrue);
      expect(machine.snapshot.phase, RecoveryPhase.runtimeVersionChecking);
      expect(machine.markVersionUnavailable(), isTrue);
      expect(machine.snapshot.phase, RecoveryPhase.runtimeVersionUnavailable);
      expect(
        machine.confirmVersion(
          currentBuild: 18100,
          latestBuild: 18201,
          updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
          recoveryUrl: 'https://quwoquan.com/',
          trustedBaseUrls: trustedBaseUrls,
        ),
        isTrue,
      );
      expect(machine.snapshot.phase, RecoveryPhase.runtimeUpdateRequired);
      expect(machine.beginRuntimeReentry(), isFalse);
    },
  );

  test('unsafe or incomplete version result never produces update copy', () {
    final machine = RecoveryStateMachine();
    expect(
      machine.confirmVersion(
        currentBuild: 18100,
        latestBuild: 18201,
        updateUrl: 'javascript:alert(1)',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupChecking);
    expect(
      machine.confirmVersion(
        currentBuild: 18100,
        latestBuild: 18201,
        updateUrl: 'https://attacker.example/quwoquan.apk',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
  });

  test('confirmed latest build does not require a native update url', () {
    final machine = RecoveryStateMachine();
    expect(
      machine.confirmVersion(
        currentBuild: 18201,
        latestBuild: 18201,
        updateUrl: '',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupLatest);
    expect(machine.snapshot.updateUrl, isEmpty);
  });
}
