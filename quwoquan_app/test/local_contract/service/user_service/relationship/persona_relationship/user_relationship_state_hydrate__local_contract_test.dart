// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/viewer-profile-state-sync-contract/spec.md#gwt-003
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';

void main() {
  group('关系投影的磁盘 hydrate 不覆盖更新的本地写入', () {
    test('hydrate 进行中发生的关注在旧快照落地后仍然保留', () async {
      final storage = _GatedRelationshipStorage(
        snapshot: <String, dynamic>{
          // 磁盘快照是启动时的旧事实：该目标尚未被关注。
          'followingPersonaIds': <String>[],
          'knownPersonaIds': <String>['persona-x'],
        },
      );
      final container = ProviderContainer(
        overrides: <Override>[
          userRelationshipStateStorageProvider.overrideWithValue(
            storage.asStorage(),
          ),
        ],
      );
      addTearDown(container.dispose);

      // build() 触发 hydrate，读取被 Completer 挂起。
      container.read(userRelationshipStateProvider);
      await Future<void>.delayed(Duration.zero);
      expect(storage.readStarted, isTrue);

      // 读取仍在进行时用户完成了一次关注：这是更新的事实。
      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('persona-x', true);
      expect(
        container.read(userRelationshipStateProvider).isFollowing('persona-x'),
        isTrue,
      );

      // 旧快照此刻才返回；它不得整包覆盖更新的本地写入。
      storage.completeRead();
      await Future<void>.delayed(Duration.zero);

      expect(
        container.read(userRelationshipStateProvider).isFollowing('persona-x'),
        isTrue,
        reason: '旧磁盘快照覆盖了更新的关注写入，跨页面关注态会丢失',
      );
    });

    test('没有并发写入时磁盘快照正常恢复', () async {
      final storage = _GatedRelationshipStorage(
        snapshot: <String, dynamic>{
          'followingPersonaIds': <String>['persona-restored'],
          'knownPersonaIds': <String>['persona-restored'],
        },
      );
      final container = ProviderContainer(
        overrides: <Override>[
          userRelationshipStateStorageProvider.overrideWithValue(
            storage.asStorage(),
          ),
        ],
      );
      addTearDown(container.dispose);

      container.read(userRelationshipStateProvider);
      await Future<void>.delayed(Duration.zero);
      storage.completeRead();
      await Future<void>.delayed(Duration.zero);

      expect(
        container
            .read(userRelationshipStateProvider)
            .isFollowing('persona-restored'),
        isTrue,
      );
    });

    test('本地写入经同一持久化边界落盘', () async {
      final storage = _GatedRelationshipStorage(snapshot: null);
      final container = ProviderContainer(
        overrides: <Override>[
          userRelationshipStateStorageProvider.overrideWithValue(
            storage.asStorage(),
          ),
        ],
      );
      addTearDown(container.dispose);

      container.read(userRelationshipStateProvider);
      await Future<void>.delayed(Duration.zero);
      storage.completeRead();
      await Future<void>.delayed(Duration.zero);

      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('persona-persisted', true);
      await Future<void>.delayed(Duration.zero);

      expect(storage.written, isNotEmpty);
      expect(
        (storage.written.last['followingPersonaIds'] as List<dynamic>).contains(
          'persona-persisted',
        ),
        isTrue,
      );
    });
    test('actor A→B→A 重建关系 notifier 且存储互不污染', () async {
      final storage = _PartitionedRelationshipStorage();
      final container = ProviderContainer(
        overrides: <Override>[
          userRelationshipStateStorageProvider.overrideWith(
            (ref) => storage.forActor(ref.watch(_testActorProvider)),
          ),
        ],
      );
      addTearDown(container.dispose);
      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('persona-a', true);
      await Future<void>.delayed(Duration.zero);
      expect(
        storage.values['A']?['followingPersonaIds'],
        contains('persona-a'),
      );
      container.read(_testActorProvider.notifier).setActor('B');
      await Future<void>.delayed(Duration.zero);
      expect(
        container.read(userRelationshipStateProvider).isFollowing('persona-a'),
        isFalse,
      );
      container
          .read(userRelationshipStateProvider.notifier)
          .setFollowing('persona-b', true);
      await Future<void>.delayed(Duration.zero);
      expect(
        storage.values['B']?['followingPersonaIds'],
        contains('persona-b'),
      );
      container.read(_testActorProvider.notifier).setActor('A');
      for (
        var attempt = 0;
        attempt < 20 &&
            !container
                .read(userRelationshipStateProvider)
                .isFollowing('persona-a');
        attempt++
      ) {
        await Future<void>.delayed(Duration.zero);
      }
      final restored = container.read(userRelationshipStateProvider);
      expect(restored.isFollowing('persona-a'), isTrue);
      expect(restored.isFollowing('persona-b'), isFalse);
      expect(
        storage.values['A']?['followingPersonaIds'],
        isNot(contains('persona-b')),
      );
    });
  });
}

/// 用 Completer 精确控制磁盘读取何时返回，从而让「读取期间的新写入」成为
/// 可重复的时序，而不是依赖真实 Hive 的偶发竞态。
final class _GatedRelationshipStorage {
  _GatedRelationshipStorage({required this.snapshot});

  final Map<String, dynamic>? snapshot;
  final Completer<void> _gate = Completer<void>();
  final List<Map<String, dynamic>> written = <Map<String, dynamic>>[];
  bool readStarted = false;

  UserRelationshipStateStorage asStorage() {
    return UserRelationshipStateStorage(read: _read, write: _write);
  }

  void completeRead() {
    if (!_gate.isCompleted) {
      _gate.complete();
    }
  }

  Future<Map<String, dynamic>?> _read() async {
    readStarted = true;
    await _gate.future;
    return snapshot;
  }

  Future<void> _write(Map<String, dynamic> value) async {
    written.add(value);
  }
}

final _testActorProvider = NotifierProvider<_TestActorNotifier, String>(
  _TestActorNotifier.new,
);

final class _TestActorNotifier extends Notifier<String> {
  @override
  String build() => 'A';
  void setActor(String value) => state = value;
}

final class _PartitionedRelationshipStorage {
  final Map<String, Map<String, dynamic>> values =
      <String, Map<String, dynamic>>{};
  UserRelationshipStateStorage forActor(String actor) =>
      UserRelationshipStateStorage(
        read: () async => values[actor],
        write: (value) async =>
            values[actor] = Map<String, dynamic>.from(value),
      );
}
