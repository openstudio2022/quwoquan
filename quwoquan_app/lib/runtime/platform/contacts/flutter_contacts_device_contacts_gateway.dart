import 'dart:async';

import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:quwoquan_app/runtime/platform/contacts/device_contacts_gateway.dart';

/// Production adapter for the native `flutter_contacts` implementation.
final class FlutterContactsDeviceContactsGateway
    implements DeviceContactsGateway {
  const FlutterContactsDeviceContactsGateway();

  @override
  bool get isSupported => true;

  @override
  Future<List<DeviceContactRecord>> readContacts({
    required Duration timeout,
  }) async {
    if (timeout.inMicroseconds <= 0) {
      throw ArgumentError.value(timeout, 'timeout', 'must be positive');
    }
    final contacts = await FlutterContacts.getAll(
      properties: const <ContactProperty>{ContactProperty.phone},
    ).timeout(timeout);
    return List<DeviceContactRecord>.unmodifiable(
      contacts.map(
        (contact) => DeviceContactRecord(
          displayName: contact.displayName?.trim() ?? '',
          phoneNumbers: List<String>.unmodifiable(
            contact.phones.map((phone) => phone.number),
          ),
        ),
      ),
    );
  }
}
