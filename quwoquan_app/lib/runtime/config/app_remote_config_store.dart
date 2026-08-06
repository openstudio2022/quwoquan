import 'package:quwoquan_app/runtime/config/app_remote_config_snapshot.dart';

/// App remote-config LKG persistence port.
///
/// Platform storage details are owned by the concrete adapter composed from
/// `runtime/di`; runtime config models depend only on this stable boundary.
abstract interface class AppRemoteConfigStore {
  Future<AppRemoteConfigSnapshot?> readActiveSnapshot();

  Future<void> writeActiveSnapshot(AppRemoteConfigSnapshot snapshot);
}
