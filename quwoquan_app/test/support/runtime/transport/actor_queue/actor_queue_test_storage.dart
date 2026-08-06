import 'package:quwoquan_app/runtime/transport/actor_queue/actor_queue_storage.dart';

/// In-memory secure-store substitute for encrypted actor queue contract tests.
final class TestActorQueueEncryptionKeyStore
    implements ActorQueueEncryptionKeyStore {
  final Map<String, String> _values = <String, String>{};

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async {
    _values[key] = value;
  }
}

ActorQueueStorage newTestActorQueueStorage() {
  return ActorQueueStorage(
    keyStore: TestActorQueueEncryptionKeyStore(),
    signalObserver: (_) {},
  );
}
