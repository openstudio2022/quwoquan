import 'package:quwoquan_app/runtime/platform/platform_capability_unavailable.dart';

/// Platform-neutral contact record exposed to business presentation code.
///
/// The runtime boundary deliberately exposes only the local display name and
/// phone strings needed for on-device hashing. Plugin objects never cross into
/// the user domain, and callers must not log or persist [phoneNumbers].
final class DeviceContactRecord {
  const DeviceContactRecord({
    required this.displayName,
    required this.phoneNumbers,
  });

  final String displayName;
  final List<String> phoneNumbers;
}

/// Anti-corruption boundary for reading the device address book.
abstract interface class DeviceContactsGateway {
  bool get isSupported;

  /// Reads phone-bearing contacts within the caller's explicit [timeout].
  Future<List<DeviceContactRecord>> readContacts({required Duration timeout});
}

/// Fail-closed composition for platforms without system-contact capability.
final class UnsupportedDeviceContactsGateway implements DeviceContactsGateway {
  const UnsupportedDeviceContactsGateway();

  @override
  bool get isSupported => false;

  @override
  Future<List<DeviceContactRecord>> readContacts({
    required Duration timeout,
  }) async {
    throw PlatformCapabilityUnavailableException(
      capability: 'contacts',
      detail: 'DeviceContactsGateway.readContacts is unavailable',
    );
  }
}
