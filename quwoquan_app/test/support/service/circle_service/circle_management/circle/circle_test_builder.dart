/// circle 对象级 typed double 使用的最小 wire。
///
/// 黄金投资圈是「预制商用 seed」：携带真实标签/简介/量级计数，
/// 供圈子高保壳层渲染契约直接消费（tags 以 ` · ` 拼接为身份副标题）。
List<Map<String, Object?>> circleWireExamples() {
  const specs = <(String, String, String)>[
    ('fixture_circle_photo', '契约摄影社', 'humanity'),
    ('fixture_circle_travel', '契约旅行手账', 'travel'),
    ('fixture_circle_gold_invest', '黄金投资圈', 'finance'),
    ('fixture_circle_photography_01', '摄影契约摄影社', 'humanity'),
    ('fixture_circle_tech_01', '科技契约科技前沿', 'tech'),
    ('fixture_circle_campus', '校园生活圈', 'campus'),
    ('fixture_circle_city', '城市漫游圈', 'travel'),
    ('fixture_circle_life', '生活方式圈', 'life'),
  ];
  return specs
      .map((spec) {
        final isGoldSeed = spec.$1 == 'fixture_circle_gold_invest';
        return <String, Object?>{
          'id': spec.$1,
          'name': spec.$2,
          'description': isGoldSeed
              ? '围绕黄金、贵金属和长期资产配置展开事实讨论。'
              : '${spec.$2} 对象级契约示例。',
          'coverUrl':
              'media/image/s/archived-image/circle/${spec.$1}/v1/cover.png',
          'avatarUrl':
              'media/avatar/s/archived-avatar/circle/${spec.$1}/v1/avatar.png',
          'ownerId': 'fixture_user_owner',
          'ownerDisplayNameSnapshot': '${spec.$2}主理人',
          'categoryId': spec.$3,
          'subCategory': spec.$3,
          'domainId': spec.$3,
          'tags': isGoldSeed
              ? const <String>['黄金', '贵金属', '资产配置']
              : <String>[spec.$3],
          'memberCount': isGoldSeed ? 8400 : 6,
          'postCount': isGoldSeed ? 1200 : 18,
          'weeklyActiveCount': isGoldSeed ? 320 : 6,
          'version': 1,
          'status': 'active',
          'visibility': 'public',
          'joinPolicy': 'open',
          'kind': 'interest',
          'displaySubjectType': 'circle',
          'followEnabled': true,
          'defaultPublicGroupId': '${spec.$1}_public',
          'autoSyncChat': true,
          'storageUsedBytes': 4096,
          'storageQuotaBytes': 1073741824,
          'createdAt': '2026-05-06T00:00:00Z',
          'updatedAt': '2026-05-06T00:00:00Z',
        };
      })
      .toList(growable: false);
}

List<Map<String, Object?>> circleStatsWireExamples() => circleWireExamples()
    .map(
      (circle) => <String, Object?>{
        'circleId': circle['id'],
        'memberCount': circle['memberCount'],
        'postCount': circle['postCount'],
        'discussionCount': circle['id'] == 'fixture_circle_gold_invest'
            ? 326
            : 0,
        'weeklyActiveCount': circle['weeklyActiveCount'],
        'likeCount': 12,
        'storageUsedBytes': 4096,
        'storageQuotaBytes': 1073741824,
      },
    )
    .toList(growable: false);

Map<String, Object?> circleImpactWireExamples() => <String, Object?>{
  'fixture_circle_photo': <String, Object?>{
    'circleId': 'fixture_circle_photo',
    'total': 1,
    'items': const <Map<String, Object?>>[
      <String, Object?>{
        'helpType': 'relationship',
        'action': 'join_circle',
        'intersectionDimension': 'relationship',
        'tagRef': 'photography',
        'source': 'circle_membership',
        'count': 1,
        'primaryText': '1位成员加入了契约摄影社',
        'subtitleText': '来自已验证的圈子成员关系',
        'impactId': 'fixture_circle_photo_membership',
        'primarySpans': <Map<String, Object?>>[
          <String, Object?>{'text': '1', 'role': 'count'},
          <String, Object?>{'text': '位成员加入了契约摄影社', 'role': 'plain'},
        ],
        'sampleVisuals': <Map<String, Object?>>[],
        'representativeActor': <String, Object?>{
          'actorId': 'fixture_user_photo',
          'displayName': '契约摄影师',
          'avatarUrl':
              'media/avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png',
          'relationLabel': '圈子成员',
          'privacyState': 'visible',
          'target': <String, Object?>{
            'objectType': 'user',
            'objectId': 'fixture_user_photo',
            'objectKind': 'person',
            'routeId': 'userProfile',
          },
          'evidenceRank': 1,
          'snapshotVersion': 'fixture_circle_photo_membership_snapshot',
        },
        'actionHints': <Map<String, Object?>>[],
        'countTarget': <String, Object?>{
          'objectType': 'circle',
          'objectId': 'fixture_circle_photo',
          'objectKind': 'circle',
          'routeId': 'circleDetail',
        },
        'evidenceSnapshotId': 'fixture_circle_photo_membership_snapshot',
        'countObjectKind': 'person',
        'iconKey': 'people',
      },
    ],
  },
};

List<Map<String, Object?>> circlePlacementWireExamples() =>
    const <Map<String, Object?>>[
      <String, Object?>{
        'circleId': 'fixture_circle_photo',
        'postId': 'fixture_photo_001',
        'status': 'active',
      },
    ];

List<Map<String, Object?>>
circleFeedPostWireExamples() => const <Map<String, Object?>>[
  <String, Object?>{
    'postId': 'fixture_photo_001',
    'contentType': 'image',
    'contentIdentity': 'work',
    'authorId': 'fixture_user_photo',
    'authorDisplayName': '契约摄影师',
    'authorAvatarUrl':
        'media/avatar/s/archived-avatar/user/fixture_user_photo/v1/avatar.png',
    'title': '西湖晨光摄影测试详情',
    'summary': '圈子 feed 对象样本',
    'mediaUrls': <String>[
      'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
    ],
    'coverUrl':
        'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
    'likeCount': 80,
    'commentCount': 0,
    'shareCount': 3,
    'createdAt': '2026-05-01T00:00:00Z',
    'updatedAt': '2026-05-01T00:00:00Z',
    'publishedAt': '2026-05-02T00:00:00Z',
  },
];

Map<String, Object?> businessCircleWireExample() => <String, Object?>{
  'circles': circleWireExamples(),
  'groups': const <String, Object?>{
    'fixture_circle_photo': <Map<String, Object?>>[
      <String, Object?>{
        '_id': 'fixture_group_photo_public',
        'circleId': 'fixture_circle_photo',
        'name': '契约摄影社公开群',
        'description': '契约摄影社默认公开群。',
        'groupType': 'public_group',
        'visibility': 'public',
        'joinPolicy': 'apply_only',
        'ownerUserId': 'fixture_user_owner',
        'conversationId': 'fixture_conv_circle_photo',
        'storageEnabled': true,
        'noticeEnabled': true,
        'isDefaultPublicGroup': true,
        'status': 'active',
        'createdAt': '2026-05-06T00:00:00Z',
        'updatedAt': '2026-05-06T00:00:00Z',
      },
    ],
  },
};
