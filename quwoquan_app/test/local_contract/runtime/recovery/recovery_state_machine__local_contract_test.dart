// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/cold-start-performance/spec.md#gwt-002
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/unrecoverable-runtime-recovery/spec.md#gwt-001
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_operation_gateway.dart';
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
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupUpdateRequired);

    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18100,
        latestBuild: 18300,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
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
          platform: RecoveryVersionPlatform.android,
          currentBuild: 18100,
          latestBuild: 18201,
          minimumSupportedBuild: 18000,
          updateState: RecoveryUpdateState.available,
          updateChannel: RecoveryVersionChannel.nativeUpdate,
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
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: 'javascript:alert(1)',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupChecking);
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: 'https://attacker.example/quwoquan.apk',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
  });

  test('confirmed latest Android build retains its canonical channel', () {
    final machine = RecoveryStateMachine();
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18201,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.none,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupLatest);
    expect(machine.snapshot.updateUrl, isEmpty);
  });

  test('typed Web-only channel settles a newer build without inference', () {
    final machine = RecoveryStateMachine();
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.ios,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.webOnly,
        updateUrl: null,
        recoveryUrl: 'https://quwoquan.com/ios',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupWebOnly);
    expect(machine.snapshot.phase.name, 'startupWebOnly');
    expect(machine.snapshot.isWebOnly, isTrue);
    expect(machine.snapshot.showsUpdate, isFalse);
    expect(machine.snapshot.showsWebSecondary, isFalse);
    expect(machine.snapshot.recoveryUrl, 'https://quwoquan.com/ios');
    expect(machine.markVersionUnavailable(), isFalse);
    expect(machine.restartVersionCheckAfterUpdate(), isFalse);
  });

  test('native-update channel rejects a missing update URL', () {
    final machine = RecoveryStateMachine();
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: null,
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupChecking);
  });

  test('runtime iOS Web-only is terminal after the single reentry budget', () {
    final machine = RecoveryStateMachine(
      initial: const RecoverySnapshot(phase: RecoveryPhase.runtimeUnavailable),
    );
    expect(machine.beginRuntimeReentry(), isTrue);
    expect(machine.failRuntimeReentry(), isTrue);
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.ios,
        currentBuild: 17000,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.required,
        updateChannel: RecoveryVersionChannel.webOnly,
        updateUrl: null,
        recoveryUrl: 'https://quwoquan.com/ios',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.runtimeWebOnly);
    expect(machine.snapshot.phase.name, 'runtimeWebOnly');
    expect(machine.snapshot.isWebOnly, isTrue);
    expect(machine.snapshot.showsUpdate, isFalse);
    expect(machine.snapshot.showsWebSecondary, isFalse);
    expect(machine.beginRuntimeReentry(), isFalse);
    expect(machine.restartVersionCheckAfterUpdate(), isFalse);
    expect(machine.markVersionUnavailable(), isFalse);
  });

  test('build below minimum is marked as a required update', () {
    final machine = RecoveryStateMachine();
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 17000,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.required,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.startupUpdateRequired);
    expect(machine.snapshot.requiresUpdate, isTrue);
  });

  test('minimum-build recovery accepts required only', () {
    final machine = RecoveryStateMachine(
      initial: const RecoverySnapshot(
        phase: RecoveryPhase.runtimeVersionChecking,
      ),
    );
    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        requiredUpdateOnly: true,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
    expect(machine.snapshot.phase, RecoveryPhase.runtimeVersionChecking);

    expect(
      machine.confirmVersion(
        platform: RecoveryVersionPlatform.android,
        currentBuild: 17000,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.required,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        requiredUpdateOnly: true,
        updateUrl: 'https://cdn.quwoquan.com/download/android/latest.json',
        recoveryUrl: 'https://quwoquan.com/',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isTrue,
    );
    expect(machine.snapshot.phase, RecoveryPhase.runtimeUpdateRequired);
    expect(machine.snapshot.requiresUpdate, isTrue);
  });

  test('platform and update channel must match the canonical matrix', () {
    final iosMachine = RecoveryStateMachine();
    expect(
      iosMachine.confirmVersion(
        platform: RecoveryVersionPlatform.ios,
        currentBuild: 18100,
        latestBuild: 18201,
        minimumSupportedBuild: 18000,
        updateState: RecoveryUpdateState.available,
        updateChannel: RecoveryVersionChannel.nativeUpdate,
        updateUrl: 'https://cdn.quwoquan.com/download/ios/latest.json',
        recoveryUrl: 'https://quwoquan.com/ios',
        trustedBaseUrls: trustedBaseUrls,
      ),
      isFalse,
    );
    expect(iosMachine.snapshot.phase, RecoveryPhase.startupChecking);

    for (final platform in <RecoveryVersionPlatform>[
      RecoveryVersionPlatform.android,
      RecoveryVersionPlatform.web,
    ]) {
      final machine = RecoveryStateMachine();
      expect(
        machine.confirmVersion(
          platform: platform,
          currentBuild: 18100,
          latestBuild: 18201,
          minimumSupportedBuild: 18000,
          updateState: RecoveryUpdateState.available,
          updateChannel: RecoveryVersionChannel.webOnly,
          updateUrl: null,
          recoveryUrl: 'https://quwoquan.com/',
          trustedBaseUrls: trustedBaseUrls,
        ),
        isFalse,
      );
      expect(machine.snapshot.phase, RecoveryPhase.startupChecking);
    }
  });
}
