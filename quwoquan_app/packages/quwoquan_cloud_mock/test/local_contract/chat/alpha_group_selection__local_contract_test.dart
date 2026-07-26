import 'package:test/test.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';

void main() {
  test('alpha selectable group source 在分页前区分私建群与圈子绑定群', () {
    final baseline = AlphaChatStateEngine();
    final candidate = baseline.listGroupCandidates(limit: 1).single;
    final friendId = candidate['userId']?.toString() ?? '';
    expect(friendId, isNotEmpty);

    Map<String, Object?> conversation({
      required String id,
      required String title,
      String circleId = '',
    }) => <String, Object?>{
      'id': id,
      'type': 'group',
      'title': title,
      'status': 'active',
      'circleId': circleId,
      'memberCount': 2,
    };

    List<Map<String, Object?>> members(String conversationId) =>
        <Map<String, Object?>>[
          <String, Object?>{
            'id': '${conversationId}_owner',
            'conversationId': conversationId,
            'userId': baseline.currentUserId,
            'displayName': '当前用户',
            'role': 'owner',
            'memberType': 'user',
          },
          <String, Object?>{
            'id': '${conversationId}_friend',
            'conversationId': conversationId,
            'userId': friendId,
            'displayName': candidate['displayName']?.toString() ?? friendId,
            'role': 'member',
            'memberType': 'user',
          },
        ];

    final engine = AlphaChatStateEngine(
      seedConversations: <Map<String, Object?>>[
        conversation(id: 'private_group', title: '私建群'),
        conversation(
          id: 'circle_group',
          title: '摄影圈交流群',
          circleId: 'circle_photo',
        ),
      ],
      seedMembers: <String, List<Map<String, Object?>>>{
        'private_group': members('private_group'),
        'circle_group': members('circle_group'),
      },
    );

    final privateRows = engine.listSelectableGroupConversations(
      source: 'group',
      limit: 20,
    );
    final circleRows = engine.listSelectableGroupConversations(
      source: 'circle',
      limit: 20,
    );

    expect(privateRows.items.map((row) => row['conversationId']), <String>[
      'private_group',
    ]);
    expect(privateRows.items.single['circleId'], '');
    expect(circleRows.items.map((row) => row['conversationId']), <String>[
      'circle_group',
    ]);
    expect(circleRows.items.single['circleId'], 'circle_photo');
    expect(circleRows.items.single['friendMemberCount'], 1);
  });

  test('alpha selectable group source 按 cursor 和服务端搜索词分页', () {
    final baseline = AlphaChatStateEngine();
    final candidate = baseline.listGroupCandidates(limit: 1).single;
    final friendId = candidate['userId']?.toString() ?? '';
    expect(friendId, isNotEmpty);

    Map<String, Object?> conversation(String id, String title) =>
        <String, Object?>{
          'id': id,
          'type': 'group',
          'title': title,
          'status': 'active',
          'memberCount': 2,
        };
    List<Map<String, Object?>> members(String conversationId) =>
        <Map<String, Object?>>[
          <String, Object?>{
            'id': '${conversationId}_owner',
            'conversationId': conversationId,
            'userId': baseline.currentUserId,
            'displayName': '当前用户',
            'role': 'owner',
            'memberType': 'user',
          },
          <String, Object?>{
            'id': '${conversationId}_friend',
            'conversationId': conversationId,
            'userId': friendId,
            'displayName': candidate['displayName']?.toString() ?? friendId,
            'role': 'member',
            'memberType': 'user',
          },
        ];
    final engine = AlphaChatStateEngine(
      seedConversations: <Map<String, Object?>>[
        conversation('group_1', '分页群一'),
        conversation('group_2', '分页群二'),
        conversation('group_3', '分页群三'),
      ],
      seedMembers: <String, List<Map<String, Object?>>>{
        'group_1': members('group_1'),
        'group_2': members('group_2'),
        'group_3': members('group_3'),
      },
    );

    final first = engine.listSelectableGroupConversations(
      source: 'group',
      limit: 1,
    );
    final second = engine.listSelectableGroupConversations(
      source: 'group',
      cursor: first.nextCursor,
      limit: 1,
    );
    final third = engine.listSelectableGroupConversations(
      source: 'group',
      cursor: second.nextCursor,
      limit: 1,
    );
    expect(
      <String>[
        ...first.items.map((row) => row['conversationId']?.toString() ?? ''),
        ...second.items.map((row) => row['conversationId']?.toString() ?? ''),
        ...third.items.map((row) => row['conversationId']?.toString() ?? ''),
      ],
      <String>['group_1', 'group_2', 'group_3'],
    );
    expect(third.nextCursor, isNull);

    final searched = engine.listSelectableGroupConversations(
      source: 'group',
      query: '分页群二',
      limit: 1,
    );
    expect(searched.items.single['conversationId'], 'group_2');
  });

  test('alpha selectable group source 拒绝未知来源值', () {
    final engine = AlphaChatStateEngine();
    expect(
      () => engine.listSelectableGroupConversations(source: 'legacy'),
      throwsArgumentError,
    );
    expect(
      () => engine.listSelectableGroupConversations(cursor: 'invalid'),
      throwsFormatException,
    );
  });
}
