import 'user_operation_contracts.g.dart';

abstract interface class ContactDiscoveryCommandWriter {
  Future<ContactDiscoveryResult> initiateContactDiscovery(
    InitiateContactDiscoveryCommand command,
  );
  Future<ContactDiscoveryDismissResult> dismissContactDiscovery(
    DismissContactDiscoveryCommand command,
  );
}

abstract interface class ContactDiscoveryQuery {
  Future<ContactDiscoveryResult> getLatestContactDiscovery(
    GetLatestContactDiscoveryQuery query,
  );
}
