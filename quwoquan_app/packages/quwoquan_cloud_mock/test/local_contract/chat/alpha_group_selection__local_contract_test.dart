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

    expect(privateRows.map((row) => row['conversationId']), <String>[
      'private_group',
    ]);
    expect(privateRows.single['circleId'], '');
    expect(circleRows.map((row) => row['conversationId']), <String>[
      'circle_group',
    ]);
    expect(circleRows.single['circleId'], 'circle_photo');
    expect(circleRows.single['friendMemberCount'], 1);
  });

  test('alpha selectable group source 拒绝未知来源值', () {
    final engine = AlphaChatStateEngine();
    expect(
      () => engine.listSelectableGroupConversations(source: 'legacy'),
      throwsArgumentError,
    );
  });
}
