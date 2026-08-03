import 'user_operation_contracts.g.dart';

abstract interface class UserHomepageQueryFacet {
  Future<UserHomepageBundleWire> getUserHomepageBundle(
    GetUserHomepageBundleQuery query,
  );
}
