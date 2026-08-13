import '../../../../runtime/identity/fixture_identity.dart';

/// user_account 对象自己的最小 profile wire 样本。
///
/// 调用方按稳定对象 ID 选择；这里不提供 named document/domain 查找。
List<Map<String, Object?>> userProfileWireExamples() {
  const identities = <(String, String, String)>[
    (fixtureCurrentUserVariantUserId, '新同学_260622_6698692', 'currentUserVariant'),
    ('fixture_user_photo', '契约摄影师', 'leadAuthor'),
    ('fixture_user_travel', '契约旅行家', 'leadAuthor'),
    ('fixture_user_article', '契约撰稿人', 'leadAuthor'),
    ('fixture_user_friend', '契约好友', 'leadAuthor'),
    ('nature_photographer', '自然摄影师', 'leadAuthor'),
  ];
  return identities
      .map(
        (identity) => <String, Object?>{
          'userId': identity.$1,
          'personaId': identity.$1,
          'ownerUserId': identity.$1,
          'userHandle': identity.$1,
          'displayName': identity.$2,
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/${identity.$1}/v1/avatar.png',
          'avatarObjectKey':
              'media/avatar/s/archived-avatar/user/${identity.$1}/v1/avatar.png',
          'backgroundUrl':
              'media/background/s/archived-avatar/user/${identity.$1}/v1/background.png',
          'backgroundObjectKey':
              'media/background/s/archived-avatar/user/${identity.$1}/v1/background.png',
          'bio': identity.$1 == 'fixture_user_current' ? '' : '对象级用户档案。',
          'primaryRole': identity.$3,
          'avatarVersion': 1,
          'followerCount': 240,
          'followingCount': 96,
          'postCount': 8,
          'circleCount': 5,
          'likeCount': 360,
          'stats': const <String, Object?>{
            'followingCount': 96,
            'followerCount': 240,
            'postCount': 8,
            'circleCount': 5,
            'likeCount': 360,
          },
          'personaRefs': const <String>[],
          'tags': const <String>['fixture', 'contact'],
          'identityTags': const <String>[],
        },
      )
      .toList(growable: false);
}

Map<String, Object?> userProfileWireExample() => <String, Object?>{
  'profiles': userProfileWireExamples(),
};
