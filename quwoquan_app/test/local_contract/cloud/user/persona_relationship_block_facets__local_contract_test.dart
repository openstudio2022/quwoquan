import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  group('PersonaRelationship block typed contract', () {
    test('BlockCommandResult 严格解析版本化结果', () {
      final result = decodeBlockCommandResult(<String, Object?>{
        'targetSubAccountId': 'ps_target',
        'blocked': true,
        'idempotentReplay': false,
        'updatedAt': '2026-07-19T12:00:00Z',
      });

      expect(result.targetSubAccountId, 'ps_target');
      expect(result.blocked, isTrue);
      expect(result.idempotentReplay, isFalse);
      expect(result.updatedAt, DateTime.utc(2026, 7, 19, 12));
    });

    test('BlockedUserSlice 解析展示快照与 nextCursor', () {
      final slice = decodeBlockedUserSlice(<String, Object?>{
        'items': <Object?>[
          <String, Object?>{
            'targetSubAccountId': 'ps_target',
            'displayName': '目标用户',
            'userHandle': 'target',
            'avatarUrl': '',
            'blockedAt': '2026-07-19T12:00:00Z',
          },
        ],
        'nextCursor': 'cursor-1',
      });

      expect(slice.items.single.displayName, '目标用户');
      expect(slice.items.single.userHandle, 'target');
      expect(slice.nextCursor, 'cursor-1');
    });

    test('缺少必填展示字段时 fail-closed', () {
      expect(
        () => decodeBlockedUserSlice(<String, Object?>{
          'items': <Object?>[
            <String, Object?>{
              'targetSubAccountId': 'ps_target',
              'blockedAt': '2026-07-19T12:00:00Z',
            },
          ],
        }),
        throwsFormatException,
      );
    });
  });

  group('AlphaPersonaRelationshipFacet', () {
    test('block/list/unblock 共用同一状态且重复命令幂等', () async {
      final facet = AlphaPersonaRelationshipFacet();
      final command = BlockUserCommand(targetSubAccountId: 'ps_target');

      final first = await facet.blockUser(command);
      final replay = await facet.blockUser(command);
      final blocked = await facet.listBlockedUsers(
        const ListBlockedUsersQuery(),
      );

      expect(first.idempotentReplay, isFalse);
      expect(replay.idempotentReplay, isTrue);
      expect(blocked.items.single.targetSubAccountId, 'ps_target');

      final unblocked = await facet.unblockUser(
        UnblockUserCommand(targetSubAccountId: 'ps_target'),
      );
      final empty = await facet.listBlockedUsers(const ListBlockedUsersQuery());

      expect(unblocked.blocked, isFalse);
      expect(empty.items, isEmpty);
    });
  });
}
