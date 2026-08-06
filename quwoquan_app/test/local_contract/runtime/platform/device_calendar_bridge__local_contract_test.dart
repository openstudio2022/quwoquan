// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-003
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/device_calendar_bridge.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum _PermitMode { valid, expired, digestMismatch }

final class _InMemoryPermitVerifier implements DeviceCalendarPermitVerifier {
  _InMemoryPermitVerifier({this.mode = _PermitMode.valid});

  final _PermitMode mode;
  final List<DeviceCalendarPermitVerification> verifications =
      <DeviceCalendarPermitVerification>[];

  @override
  Future<DeviceCalendarVerifiedPermit> verify(
    DeviceCalendarPermitVerification verification,
  ) async {
    verifications.add(verification);
    return DeviceCalendarVerifiedPermit(
      installationId: verification.installationId,
      deviceId: verification.deviceId,
      capability: verification.capability,
      inputDigest: mode == _PermitMode.digestMismatch
          ? 'sha256:${List<String>.filled(64, 'f').join()}'
          : verification.inputDigest,
      idempotencyKey: verification.idempotencyKey,
      expiresAt: mode == _PermitMode.expired
          ? verification.verifiedAt.subtract(const Duration(seconds: 1))
          : verification.verifiedAt.add(const Duration(minutes: 5)),
    );
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const channel = MethodChannel('quwoquan/assistant/device_action');
  final now = DateTime.utc(2026, 8, 6, 6);
  final binding = const DeviceCalendarLocalBinding(
    installationId: 'installation-7',
    deviceId: 'device-9',
  );
  final createRequest = DeviceCalendarCreateRequest(
    permitId: 'opaque-permit-create',
    idempotencyKey: 'calendar-create-1',
    calendarId: 'calendar-local',
    title: '行程提醒',
    start: DateTime.utc(2026, 8, 8, 1),
    end: DateTime.utc(2026, 8, 8, 2),
    timezone: 'Asia/Shanghai',
    location: '西湖',
    notes: '仅用于原生参数合同测试',
  );

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  group('CapabilityProfile 驱动同一 DeviceCalendar 行为合同', () {
    final profiles = <String, PlatformCapabilities>{
      'mobile': CapabilityProfile.mobile,
      'web': CapabilityProfile.web,
      'ohos': CapabilityProfile.ohos,
    };

    for (final entry in profiles.entries) {
      test('${entry.key}: capability 与装配一致', () async {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, (call) async {
              expect(call.method, 'probe');
              return <String, Object>{
                'availability': 'available',
                'permission': 'granted',
                'hasWritableCalendar': true,
              };
            });
        final container = ProviderContainer(
          overrides: <Override>[
            platformCapabilitiesProvider.overrideWithValue(entry.value),
            deviceCalendarPermitVerifierProvider.overrideWithValue(
              _InMemoryPermitVerifier(),
            ),
            deviceCalendarLocalBindingProvider.overrideWithValue(binding),
          ],
        );
        addTearDown(container.dispose);

        final bridge = container.read(deviceCalendarBridgeProvider);
        expect(entry.value.deviceCalendar, entry.key == 'mobile');
        if (entry.value.deviceCalendar) {
          expect(bridge, isA<MethodChannelDeviceCalendarBridge>());
          expect((await bridge.probe()).canMutate, isTrue);
        } else {
          expect(bridge, isA<UnsupportedDeviceCalendarBridge>());
          final probe = await bridge.probe();
          expect(probe.canMutate, isFalse);
          expect(probe.failure?.kind, RuntimeFailureKind.unavailable);
        }
      });
    }
  });

  test('permission denied 映射结构化 RuntimeFailure', () async {
    final verifier = _InMemoryPermitVerifier();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          expect(call.method, 'createEvent');
          return <String, Object>{'status': 'permission_denied'};
        });
    final bridge = MethodChannelDeviceCalendarBridge(
      channel: channel,
      permitVerifier: verifier,
      localBinding: binding,
      clock: () => now,
    );

    await expectLater(
      bridge.create(createRequest),
      throwsA(
        isA<DeviceCalendarException>()
            .having(
              (error) => error.reason,
              'reason',
              DeviceCalendarFailureReason.permissionDenied,
            )
            .having(
              (error) => error.runtimeFailure.kind,
              'kind',
              RuntimeFailureKind.permission,
            )
            .having(
              (error) => error.runtimeFailure.nature,
              'nature',
              RuntimeFailureNature.requiresPermission,
            ),
      ),
    );
  });

  test('restricted/no calendar/not found/system error 映射可区分失败', () async {
    final cases = <String, DeviceCalendarFailureReason>{
      'permission_restricted': DeviceCalendarFailureReason.permissionRestricted,
      'no_calendar': DeviceCalendarFailureReason.noWritableCalendar,
      'event_not_found': DeviceCalendarFailureReason.eventNotFound,
      'system_error': DeviceCalendarFailureReason.systemError,
    };
    for (final entry in cases.entries) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            channel,
            (_) async => <String, Object>{'status': entry.key},
          );
      final bridge = MethodChannelDeviceCalendarBridge(
        channel: channel,
        permitVerifier: _InMemoryPermitVerifier(),
        localBinding: binding,
        clock: () => now,
      );
      final mutation = entry.key == 'event_not_found'
          ? bridge.update(
              DeviceCalendarUpdateRequest(
                permitId: 'opaque-permit-update',
                idempotencyKey: 'not-found-update',
                deviceEventId: 'missing-event',
                title: '行程提醒',
                start: DateTime.utc(2026, 8, 8, 1),
                end: DateTime.utc(2026, 8, 8, 2),
                timezone: 'Asia/Shanghai',
              ),
            )
          : bridge.create(createRequest);
      await expectLater(
        mutation,
        throwsA(
          isA<DeviceCalendarException>().having(
            (error) => error.reason,
            'reason',
            entry.value,
          ),
        ),
      );
    }
  });

  test('expired permit 与 digest mismatch 在触达原生前拒绝', () async {
    var nativeCalls = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          nativeCalls += 1;
          return <String, Object>{'status': 'system_error'};
        });

    for (final mode in <_PermitMode>[
      _PermitMode.expired,
      _PermitMode.digestMismatch,
    ]) {
      final bridge = MethodChannelDeviceCalendarBridge(
        channel: channel,
        permitVerifier: _InMemoryPermitVerifier(mode: mode),
        localBinding: binding,
        clock: () => now,
      );
      await expectLater(
        bridge.create(createRequest),
        throwsA(
          isA<DeviceCalendarException>().having(
            (error) => error.reason,
            'reason',
            mode == _PermitMode.expired
                ? DeviceCalendarFailureReason.permitExpired
                : DeviceCalendarFailureReason.permitBindingMismatch,
          ),
        ),
      );
    }
    expect(nativeCalls, 0);
  });

  test('create/update/delete 只返回 opaque receipt 且进程内重放不重复执行', () async {
    final calls = <MethodCall>[];
    final receiptDigest = 'sha256:${List<String>.filled(64, 'a').join()}';
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          calls.add(call);
          final arguments = (call.arguments! as Map<Object?, Object?>);
          expect(arguments.containsKey('permitId'), isFalse);
          expect(
            arguments['inputDigest'],
            matches(RegExp(r'^sha256:[0-9a-f]{64}$')),
          );
          final eventId = call.method == 'createEvent'
              ? 'event-created'
              : arguments['deviceEventId']! as String;
          return <String, Object>{
            'status': 'succeeded',
            'deviceEventId': eventId,
            'receiptDigest': receiptDigest,
            'replayed': false,
          };
        });
    final verifier = _InMemoryPermitVerifier();
    final bridge = MethodChannelDeviceCalendarBridge(
      channel: channel,
      permitVerifier: verifier,
      localBinding: binding,
      clock: () => now,
    );

    final created = await bridge.create(createRequest);
    final replayed = await bridge.create(createRequest);
    final updated = await bridge.update(
      DeviceCalendarUpdateRequest(
        permitId: 'opaque-permit-update',
        idempotencyKey: 'calendar-update-1',
        deviceEventId: created.deviceEventId,
        calendarId: 'calendar-local',
        title: '行程提醒（已更新）',
        start: DateTime.utc(2026, 8, 8, 2),
        end: DateTime.utc(2026, 8, 8, 3),
        timezone: 'Asia/Shanghai',
        location: '灵隐寺',
        notes: '更新合同',
      ),
    );
    final deleted = await bridge.delete(
      DeviceCalendarDeleteRequest(
        permitId: 'opaque-permit-delete',
        idempotencyKey: 'calendar-delete-1',
        deviceEventId: created.deviceEventId,
      ),
    );

    expect(created.deviceEventId, 'event-created');
    expect(created.receiptDigest, receiptDigest);
    expect(replayed.replayed, isTrue);
    expect(updated.deviceEventId, 'event-created');
    expect(deleted.deviceEventId, 'event-created');
    expect(calls.map((call) => call.method), <String>[
      'createEvent',
      'updateEvent',
      'deleteEvent',
    ]);
    expect(verifier.verifications.map((item) => item.capability), <String>[
      'calendar.event.create',
      'calendar.event.create',
      'calendar.event.update',
      'calendar.event.delete',
    ]);
    expect(
      verifier.verifications.map((item) => item.installationId).toSet(),
      <String>{'installation-7'},
    );
    expect(
      verifier.verifications.map((item) => item.deviceId).toSet(),
      <String>{'device-9'},
    );
    expect(verifier.verifications.map((item) => item.idempotencyKey), <String>[
      'calendar-create-1',
      'calendar-create-1',
      'calendar-update-1',
      'calendar-delete-1',
    ]);
  });

  test('production verifier 未接 generated auth 时 fail-closed', () async {
    var nativeCalls = 0;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (_) async {
          nativeCalls += 1;
          return <String, Object>{'status': 'succeeded'};
        });
    final bridge = MethodChannelDeviceCalendarBridge(
      channel: channel,
      permitVerifier: const FailClosedDeviceCalendarPermitVerifier(),
      localBinding: binding,
      clock: () => now,
    );

    await expectLater(
      bridge.create(createRequest),
      throwsA(
        isA<DeviceCalendarException>().having(
          (error) => error.reason,
          'reason',
          DeviceCalendarFailureReason.permitVerifierUnavailable,
        ),
      ),
    );
    expect(nativeCalls, 0);
  });

  test('Unsupported bridge 对 Web/OHOS 返回 structured unavailable', () async {
    const bridge = UnsupportedDeviceCalendarBridge();
    final probe = await bridge.probe();
    expect(probe.availability, DeviceCalendarAvailability.unavailable);
    expect(probe.failure?.kind, RuntimeFailureKind.unavailable);
    await expectLater(
      bridge.create(createRequest),
      throwsA(
        isA<DeviceCalendarException>()
            .having(
              (error) => error.reason,
              'reason',
              DeviceCalendarFailureReason.unavailable,
            )
            .having(
              (error) => error.runtimeFailure.kind,
              'kind',
              RuntimeFailureKind.unavailable,
            ),
      ),
    );
  });
}
