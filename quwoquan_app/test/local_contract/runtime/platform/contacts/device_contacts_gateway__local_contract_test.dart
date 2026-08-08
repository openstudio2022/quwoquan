// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/platform/contacts/device_contacts_gateway.dart';
import 'package:quwoquan_app/runtime/platform/contacts/flutter_contacts_device_contacts_gateway.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';

void main() {
  test('mobile 只装配真实 flutter contacts 防腐层', () {
    final container = ProviderContainer(
      overrides: <Override>[
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
      ],
    );
    addTearDown(container.dispose);

    final gateway = container.read(deviceContactsGatewayProvider);
    expect(gateway, isA<FlutterContactsDeviceContactsGateway>());
    expect(gateway.isSupported, isTrue);
  });

  for (final entry in <String, PlatformCapabilities>{
    'web': CapabilityProfile.web,
    'ohos': CapabilityProfile.ohos,
  }.entries) {
    test('${entry.key} 以结构化 unavailable fail-close', () async {
      final container = ProviderContainer(
        overrides: <Override>[
          platformCapabilitiesProvider.overrideWithValue(entry.value),
        ],
      );
      addTearDown(container.dispose);

      final gateway = container.read(deviceContactsGatewayProvider);
      expect(gateway, isA<UnsupportedDeviceContactsGateway>());
      await expectLater(
        gateway.readContacts(timeout: const Duration(seconds: 1)),
        throwsA(
          isA<PlatformCapabilityUnavailableException>().having(
            (error) => error.capability,
            'capability',
            'contacts',
          ),
        ),
      );
    });
  }

  test('production adapter 在触达插件前拒绝无界读取', () async {
    const gateway = FlutterContactsDeviceContactsGateway();

    await expectLater(
      gateway.readContacts(timeout: Duration.zero),
      throwsA(isA<ArgumentError>()),
    );
  });
}
