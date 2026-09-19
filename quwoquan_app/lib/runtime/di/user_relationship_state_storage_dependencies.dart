import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/actor_interaction_partition.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';

const String userRelationshipStateStorageKey = 'user_relationship_state';

final class UserRelationshipStateStorage {
  const UserRelationshipStateStorage({required this.read, required this.write});
  final Future<Map<String, dynamic>?> Function() read;
  final Future<void> Function(Map<String, dynamic>) write;
}

final userRelationshipStateStorageProvider =
    Provider<UserRelationshipStateStorage>((ref) {
      final key = ref
          .watch(actorInteractionPartitionProvider)
          .boxName(userRelationshipStateStorageKey);
      return UserRelationshipStateStorage(
        read: () => readPersistedInteractionMap(key),
        write: (value) => writePersistedInteractionMap(key, value),
      );
    });
