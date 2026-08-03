import 'user_operation_contracts.g.dart';

abstract interface class AccountLifecycleCommandWriter {
  Future<CloseAccountResultWire> closeAccount(CloseAccountCommand command);
}
