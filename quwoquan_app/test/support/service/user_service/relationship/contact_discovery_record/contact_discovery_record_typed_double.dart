import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha-only 通讯录匹配 Facet。
///
/// contract fixture 不伪造设备通讯录命中；发起匹配只产生合法空结果。
final class InMemoryContactDiscoveryFacet
    implements ContactDiscoveryCommandWriter, ContactDiscoveryQuery {
  int _sequence = 0;
  ContactDiscoveryResult? _latest;

  @override
  Future<ContactDiscoveryResult> initiateContactDiscovery(
    InitiateContactDiscoveryCommand command,
  ) async {
    final now = DateTime.now().toUtc();
    final result = ContactDiscoveryResult(
      id: 'alpha-contact-discovery-${++_sequence}',
      status: DiscoveryStatus.completed,
      matchedPersonaIds: const <String>[],
      matchCount: 0,
      matches: const <ContactDiscoveryMatchResult>[],
      completedAt: now,
    );
    _latest = result;
    return result;
  }

  @override
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  ) async {
    return _latest ??
        ContactDiscoveryResult(
          id: '',
          status: DiscoveryStatus.completed,
          matchedPersonaIds: <String>[],
          matchCount: 0,
          matches: <ContactDiscoveryMatchResult>[],
        );
  }

  @override
  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  ) async {
    if (_latest?.id == command.discoveryId) {
      _latest = null;
    }
    return ContactDiscoveryDismissResult(
      status: DiscoveryStatus.dismissed,
    );
  }
}
