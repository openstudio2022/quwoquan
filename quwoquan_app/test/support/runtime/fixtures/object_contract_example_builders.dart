import 'dart:convert';

import '../../service/content_service/content/post/home_showcase_core_fixture.g.dart';

/// Deterministic local-contract object builders for the three former scenario
/// dumps. They keep a few named examples and generate size boundaries in
/// memory; environment/UAT code cannot import this test-only library.
Map<String, Object?> buildObjectContractExampleDocument(String domain) {
  switch (domain) {
    case 'chat':
      return _chatDocument();
    case 'circle':
      return _circleDocument();
    case 'content':
      return _contentDocument();
    case 'user':
      return _userDocument();
    case 'tag':
      return _tagDocument();
    default:
      throw ArgumentError.value(domain, 'domain', 'has no object builder');
  }
}

Map<String, Object?> _circleDocument() {
  const circleIds = <String>[
    'fixture_circle_photo',
    'fixture_circle_travel',
    'fixture_circle_gold_invest',
    'fixture_circle_photography_01',
    'fixture_circle_tech_01',
    'fixture_circle_campus',
    'fixture_circle_city',
    'fixture_circle_life',
  ];
  final circles = <Map<String, Object?>>[
    _circle(
      id: circleIds[0],
      name: '契约摄影社',
      ownerId: 'fixture_user_owner',
      category: 'humanity',
      subCategory: '影像',
      domainId: 'culture_arts',
    ),
    _circle(
      id: circleIds[1],
      name: '契约旅行手账',
      ownerId: 'fixture_user_travel_owner',
      category: 'travel',
      subCategory: '攻略',
      domainId: 'culture_arts',
    ),
    _circle(
      id: circleIds[2],
      name: '黄金投资圈',
      ownerId: 'fixture_user_article',
      category: 'finance',
      subCategory: '黄金',
      domainId: 'finance',
    ),
    _circle(
      id: circleIds[3],
      name: '摄影契约摄影社',
      ownerId: 'fixture_user_photo',
      category: 'humanity',
      subCategory: '影像',
      domainId: 'culture_arts',
    ),
    _circle(
      id: circleIds[4],
      name: '科技契约科技前沿',
      ownerId: 'fixture_user_tech_01',
      category: 'tech',
      subCategory: 'AI',
      domainId: 'tech',
    ),
    _circle(
      id: circleIds[5],
      name: '校园生活圈',
      ownerId: 'fixture_user_current',
      category: 'campus',
      subCategory: '校园',
      domainId: 'education',
    ),
    _circle(
      id: circleIds[6],
      name: '城市漫游圈',
      ownerId: 'fixture_user_travel',
      category: 'travel',
      subCategory: '城市',
      domainId: 'culture_arts',
    ),
    _circle(
      id: circleIds[7],
      name: '生活方式圈',
      ownerId: 'fixture_user_friend',
      category: 'life',
      subCategory: '生活',
      domainId: 'lifestyle',
    ),
  ];
  final stats = circles
      .map(
        (circle) => <String, Object?>{
          'circleId': circle['id'],
          'memberCount': circle['memberCount'],
          'postCount': circle['postCount'],
          'discussionCount': 0,
          'weeklyActiveCount': circle['weeklyActiveCount'],
          'likeCount': 12,
          'storageUsedBytes': 4096,
          'storageQuotaBytes': 1073741824,
        },
      )
      .toList(growable: false);
  return <String, Object?>{
    'examples': <String, Object?>{
      'circle_core': <String, Object?>{
        'description': 'eight named circle examples built in memory',
        'circles': circles,
        'groups': <String, Object?>{
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
      },
      'circle_home_feed_core': <String, Object?>{
        'featuredCircleIds': circleIds.take(6).toList(growable: false),
        'groupFeedPostIds': const <String>[
          'fixture_photo_001',
          'fixture_article_001',
          'fixture_video_001',
        ],
      },
      'circle_profile_core': <String, Object?>{
        'circleIds': circleIds,
        'stats': stats,
        'impacts': <String, Object?>{
          'fixture_circle_photo': _circlePhotoImpact(),
        },
        'placements': const <Map<String, Object?>>[
          <String, Object?>{
            'circleId': 'fixture_circle_photo',
            'postId': 'fixture_photo_001',
            'status': 'active',
          },
          <String, Object?>{
            'circleId': 'fixture_circle_travel',
            'postId': 'fixture_article_001',
            'status': 'active',
          },
          <String, Object?>{
            'circleId': 'fixture_circle_photography_01',
            'postId': 'fixture_post_photography_001',
            'status': 'active',
          },
        ],
      },
    },
  };
}

Map<String, Object?> _circle({
  required String id,
  required String name,
  required String ownerId,
  required String category,
  required String subCategory,
  required String domainId,
}) => <String, Object?>{
  'id': id,
  'name': name,
  'description': '$name 对象级契约示例。',
  'coverUrl': 'media/image/s/archived-image/circle/$id/v1/cover.png',
  'avatarUrl': 'media/avatar/s/archived-avatar/circle/$id/v1/avatar.png',
  'ownerId': ownerId,
  'ownerDisplayNameSnapshot': '$name 主理人',
  'categoryId': category,
  'subCategory': subCategory,
  'domainId': domainId,
  'tags': <String>[category, subCategory],
  'memberCount': 6,
  'postCount': 18,
  'weeklyActiveCount': 6,
  'version': 1,
  'status': 'active',
  'visibility': 'public',
  'joinPolicy': 'open',
  'kind': 'interest',
  'displaySubjectType': 'circle',
  'followEnabled': true,
  'defaultPublicGroupId': '${id}_public',
  'conversationId': 'fixture_conv_$id',
  'autoSyncChat': true,
  'storageUsedBytes': 4096,
  'storageQuotaBytes': 1073741824,
  'createdAt': '2026-05-06T00:00:00Z',
  'updatedAt': '2026-05-06T00:00:00Z',
};

Map<String, Object?> _circlePhotoImpact() => <String, Object?>{
  'circleId': 'fixture_circle_photo',
  'total': 1,
  'items': <Map<String, Object?>>[
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
};

Map<String, Object?> _tagDocument() {
  const chinaRoot = 'Topic/地理/行政区/中国';
  const guangdong = '$chinaRoot/广东省';
  const occupationRoot = 'Audience/用户/职业';
  const productOps = '$occupationRoot/产品运营';
  const interestRoot = 'Audience/用户/兴趣偏好';
  const travelPhoto = '$interestRoot/旅行摄影';
  final provinces = _provinceLabels
      .map(
        (label) => _tagChild(
          parent: chinaRoot,
          label: label,
          displayLabel: _shortAdministrativeLabel(label),
          depth: 4,
          hasChildren: true,
        ),
      )
      .toList(growable: false);
  final guangdongCities = <Map<String, Object?>>[
    _tagChild(parent: guangdong, label: '广州市', displayLabel: '广州'),
    _tagChild(parent: guangdong, label: '深圳市', displayLabel: '深圳'),
    _tagChild(parent: guangdong, label: '珠海市', displayLabel: '珠海'),
  ];
  final occupations = <Map<String, Object?>>[
    _tagChild(
      parent: occupationRoot,
      label: '产品运营',
      displayLabel: '产品/运营',
      hasChildren: true,
    ),
    _tagChild(
      parent: occupationRoot,
      label: '研发技术',
      displayLabel: '研发/技术',
      hasChildren: true,
    ),
    _tagChild(parent: occupationRoot, label: '学生', hasChildren: true),
  ];
  final productRoles = <Map<String, Object?>>[
    _tagChild(parent: productOps, label: '产品经理'),
    _tagChild(parent: productOps, label: '产品运营'),
  ];
  final travelInterests = <Map<String, Object?>>[
    _tagChild(parent: travelPhoto, label: '旅行'),
    _tagChild(parent: travelPhoto, label: '摄影'),
    _tagChild(parent: travelPhoto, label: '城市漫游'),
  ];
  final validRefs = <String>{
    'Topic/主题/自然风光',
    for (final child in <Map<String, Object?>>[
      ...provinces,
      ...guangdongCities,
      ...occupations,
      ...productRoles,
      ...travelInterests,
    ])
      child['tagRef']! as String,
  };
  return <String, Object?>{
    'examples': <String, Object?>{
      'tag_catalog_core': <String, Object?>{
        'description': 'named contract examples generated with a fixed seed',
        'childrenByParent': <String, Object?>{
          chinaRoot: provinces,
          guangdong: guangdongCities,
          occupationRoot: occupations,
          productOps: productRoles,
          travelPhoto: travelInterests,
        },
        'validTagRefs': validRefs.toList(growable: false),
      },
    },
  };
}

Map<String, Object?> _tagChild({
  required String parent,
  required String label,
  String? displayLabel,
  int depth = 4,
  bool hasChildren = false,
}) => <String, Object?>{
  'tagRef': '$parent/$label',
  'label': label,
  'displayLabel': displayLabel ?? label,
  'labelEn': '',
  'parentTagRef': parent,
  'depth': depth,
  'hasChildren': hasChildren,
  'releaseId': 'tag-catalog-current',
  'lifecycleStatus': 'active',
};

String _shortAdministrativeLabel(String label) => label
    .replaceFirst('特别行政区', '')
    .replaceFirst('壮族自治区', '')
    .replaceFirst('回族自治区', '')
    .replaceFirst('维吾尔自治区', '')
    .replaceFirst('自治区', '')
    .replaceFirst('省', '')
    .replaceFirst('市', '');

const List<String> _provinceLabels = <String>[
  '广东省',
  '北京市',
  '上海市',
  '浙江省',
  '江苏省',
  '四川省',
  '重庆市',
  '福建省',
  '湖北省',
  '湖南省',
  '山东省',
  '河南省',
  '河北省',
  '安徽省',
  '广西壮族自治区',
  '海南省',
  '天津市',
  '山西省',
  '内蒙古自治区',
  '辽宁省',
  '吉林省',
  '黑龙江省',
  '江西省',
  '贵州省',
  '云南省',
  '西藏自治区',
  '陕西省',
  '甘肃省',
  '青海省',
  '宁夏回族自治区',
  '新疆维吾尔自治区',
  '香港特别行政区',
  '澳门特别行政区',
  '台湾省',
];

Map<String, Object?> _contentDocument() {
  final discoveryPosts = List<Map<String, Object?>>.generate(
    _contentPostIds.length,
    _contentPost,
    growable: false,
  );
  final homePosts = (jsonDecode(kHomeShowcaseCorePostsJson) as List<Object?>)
      .whereType<Map<Object?, Object?>>()
      .map(_stringMap)
      .toList(growable: false);
  final discoveryComments = List<Map<String, Object?>>.generate(
    5,
    (index) => _comment(
      id: 'fixture_comment_${_contentPostIds[index + 1]}',
      postId: _contentPostIds[index + 1],
      index: index,
    ),
    growable: false,
  );
  return <String, Object?>{
    'examples': <String, Object?>{
      'content_discovery_core': <String, Object?>{
        'description': 'ten named object examples built in memory',
        'posts': discoveryPosts,
        'reactions': List<Map<String, Object?>>.generate(
          6,
          (index) => <String, Object?>{
            'postId': _contentPostIds[index],
            'userId': index.isEven
                ? 'fixture_user_current'
                : 'fixture_user_friend',
            'liked': true,
            'favorited': index < 3,
          },
          growable: false,
        ),
        'comments': discoveryComments,
      },
      'home_showcase_core': <String, Object?>{
        'description': 'generated UI form examples and generated comments',
        'posts': homePosts,
        'comments': List<Map<String, Object?>>.generate(
          309,
          (index) => _comment(
            id: 'home_showcase_comment_${index + 1}',
            postId: (homePosts[index % homePosts.length]['postId'] ?? '')
                .toString(),
            index: index,
          ),
          growable: false,
        ),
      },
      'comment_thread_core': <String, Object?>{
        'description': 'fixed-seed 182-comment paging boundary',
        'comments': List<Map<String, Object?>>.generate(
          182,
          (index) => _comment(
            id: index == 0
                ? 'fixture_comment_parent_001'
                : index == 1
                ? 'fixture_comment_reply_001'
                : 'fixture_comment_boundary_${index + 1}',
            postId: 'fixture_photo_001',
            index: index,
            replyTo: index == 1 ? 'fixture_comment_parent_001' : '',
          ),
          growable: false,
        ),
      },
      'footprint_core': <String, Object?>{
        'items': <Map<String, Object?>>[
          _footprint('fixture_photo_001', 'click', 'viewed', 2),
          _footprint('fixture_article_001', 'content_depth', 'viewed', 8),
          _footprint('fixture_photo_001', 'like', 'liked', 26),
          _footprint('fixture_article_001', 'comment', 'commented', 50),
          _footprint('fixture_photo_001', 'share', 'shared', 96),
        ],
      },
      'intersection_core': _intersectionCore(),
      'profile_share_interaction_core': <String, Object?>{
        'profileShareInteractions': _profileShareInteractions(),
      },
    },
  };
}

const List<String> _contentPostIds = <String>[
  'fixture_photo_001',
  'fixture_photo_002',
  'fixture_video_001',
  'fixture_article_001',
  'fixture_moment_001',
  'fixture_post_photography_001',
  'fixture_post_lifestyle_001',
  'fixture_video_002',
  'fixture_moment_002',
  'fixture_moment_003',
];

Map<String, Object?> _contentPost(int index) {
  final id = _contentPostIds[index];
  final contentType = id.contains('video')
      ? 'video'
      : id.contains('article')
      ? 'article'
      : id.contains('moment')
      ? 'micro'
      : 'image';
  final authorId = index < 2 || index == 5
      ? 'fixture_user_photo'
      : index == 2
      ? 'fixture_user_travel'
      : index == 3
      ? 'fixture_user_article'
      : 'fixture_user_current';
  final authorName = authorId == 'fixture_user_photo'
      ? '契约摄影师'
      : authorId == 'fixture_user_travel'
      ? '契约旅行家'
      : authorId == 'fixture_user_article'
      ? '契约撰稿人'
      : '新同学_260622_6698692';
  final mediaBase = 'media/image/s/archived-image/post/$id/v1';
  final post = <String, Object?>{
    'postId': id,
    'contentType': contentType,
    'contentIdentity': contentType == 'micro' ? 'moment' : 'work',
    'authorId': authorId,
    'personaId': authorId,
    'authorDisplayName': authorName,
    'authorDisplayNameSnapshot': authorName,
    'authorAvatarUrl': _avatar(authorId),
    'authorAvatarObjectKey': _avatar(authorId),
    'avatarObjectKey': _avatar(authorId),
    'authorBackgroundUrl': _background(authorId),
    'authorBackgroundObjectKey': _background(authorId),
    'title': <String>[
      '西湖晨光摄影测试详情',
      '城市傍晚的光影层次',
      '杭州一日游契约视频',
      '契约驱动的发现页文章',
      '契约周末早餐',
      '晨光 #1',
      '窗边 #1',
      '城市夜游契约视频',
      '午后散步契约动态',
      '周末读书契约动态',
    ][index],
    'summary': '固定 seed 对象样本 ${index + 1}',
    'body': '固定 seed 对象样本正文 ${index + 1}',
    'coverUrl': '$mediaBase/cover.png',
    'thumbnailUrl': '$mediaBase/cover.png',
    'mediaUrls': <String>['$mediaBase/cover.png', '$mediaBase/image-2.png'],
    'coverObjectKey': '$mediaBase/cover.png',
    'thumbnailObjectKey': '$mediaBase/cover.png',
    'mediaObjectKeys': <String>[
      '$mediaBase/cover.png',
      '$mediaBase/image-2.png',
    ],
    'imageObjectKeys': <String>[
      '$mediaBase/cover.png',
      '$mediaBase/image-2.png',
    ],
    'width': 1280,
    'height': contentType == 'image' ? 960 : 720,
    'likeCount': 80 + index * 17,
    'commentCount': index == 0 ? 0 : 1,
    'favoriteCount': 20 + index,
    'shareCount': 3 + index,
    'createdAt': '2026-05-01T0${index}:00:00Z',
    'updatedAt': '2026-05-01T0${index}:00:00Z',
    'publishedAt': '2026-05-02T0${index}:00:00Z',
    'tagRefs': <String>['fixture', contentType],
    'circleIds': <String>['fixture_circle_photo'],
    'circleNames': <String>['契约摄影社'],
    'circleId': 'fixture_circle_photo',
    'circleName': '契约摄影社',
    'locationName': index == 0 ? '杭州西湖' : '杭州',
  };
  if (contentType == 'video') {
    post['videoUrl'] =
        'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4';
    post['durationMs'] = 45000;
  }
  if (contentType == 'article') {
    post['articleMarkdown'] = '# 契约驱动的发现页文章\n\n固定 seed 长文正文。';
    post['markdownDialect'] = 'qwq-rich-md';
    post['articleRenderProfile'] = <String, Object?>{
      'template': 'journal',
      'fontPreset': 'clean',
      'layoutPolicy': <String, Object?>{
        'wrapDowngrade': 'compactWidthToFullWidth',
        'galleryDowngrade': 'singleColumn',
      },
    };
  }
  return post;
}

Map<String, Object?> _comment({
  required String id,
  required String postId,
  required int index,
  String replyTo = '',
}) => <String, Object?>{
  'commentId': id,
  '_id': id,
  'postId': postId,
  'authorId': index.isEven ? 'fixture_user_current' : 'fixture_user_friend',
  'authorDisplayNameSnapshot': index.isEven ? '新同学_260622_6698692' : '契约好友',
  'authorAvatarUrlSnapshot': _avatar(
    index.isEven ? 'fixture_user_current' : 'fixture_user_friend',
  ),
  'content': '固定 seed 评论 ${index + 1}',
  'createdAt': DateTime.utc(
    2026,
    6,
    5,
  ).add(Duration(minutes: index)).toIso8601String(),
  'replyToCommentId': replyTo,
  if (replyTo.isNotEmpty) 'parentCommentId': replyTo,
  if (replyTo.isNotEmpty) 'replyToUserId': 'fixture_user_current',
  'likeCount': index == 0 ? 128 : index % 13,
  'hotScore': index == 0 ? 128.0 : (index % 13).toDouble(),
  if (index == 0) 'replyCount': 1,
};

Map<String, Object?> _footprint(
  String postRef,
  String action,
  String type,
  int hours,
) => <String, Object?>{
  'postRef': postRef,
  'action': action,
  'type': type,
  'occurredAgoHours': hours,
};

Map<String, Object?> _intersectionCore() {
  const objectKinds = <String>[
    'route',
    'photo_spot',
    'gear',
    'place',
    'circle',
    'person',
    'route',
  ];
  const lifecycles = <String>[
    'new',
    'strengthened',
    'stable',
    'weakened',
    'reactivated',
    'archived',
    'expired',
  ];
  final reasons = List<Map<String, Object?>>.generate(
    objectKinds.length,
    (index) => _intersectionReason(
      index: index,
      objectKind: objectKinds[index],
      lifecycle: lifecycles[index],
    ),
    growable: false,
  );
  return <String, Object?>{
    'inboxReasons': reasons,
    'objectIntersections': <String, Object?>{
      'fixture_homepage_travel_route_erhai': <Object?>[reasons[0]],
      'fixture_homepage_travel_spot_duanqiao': <Object?>[reasons[1]],
      'u_lin': <Object?>[reasons[5]],
      'c_photo': <Object?>[reasons[4]],
      'e_pku': <Object?>[reasons[3]],
    },
    'authorImpact': <String, Object?>{
      'fixture_user_travel_curator': _authorImpact(
        'fixture_user_travel_curator',
      ),
      'fixture_user_current': _authorImpact('fixture_user_current'),
    },
  };
}

Map<String, Object?> _intersectionReason({
  required int index,
  required String objectKind,
  required String lifecycle,
}) {
  final objectId = 'fixture_homepage_travel_${objectKind}_$index';
  final objectText = '旅行对象${index + 1}';
  final primaryText = '林清越也看过「$objectText」';
  final personTarget = _target(
    'user',
    'fixture_user_lin',
    'person',
    'userProfile',
  );
  final objectTarget = _target(
    objectKind == 'person' ? 'user' : 'homepage',
    objectId,
    objectKind,
    <String>{'route', 'photo_spot', 'gear'}.contains(objectKind)
        ? 'homepageDetail'
        : objectKind == 'circle'
        ? 'circleDetail'
        : objectKind == 'person'
        ? 'userProfile'
        : 'homepageDetail',
  );
  return <String, Object?>{
    'intersectionId': 'ix_lm_${index + 1}',
    'kind': 'relationship',
    'vertical': 'travel_photography',
    'dimension': index.isEven ? 'location' : 'relationship',
    'intersectionClass': 'fact',
    'objectKind': objectKind,
    'relationObjectId': objectId,
    'actionType': 'view_object',
    'actionTargetId': objectId,
    'source': 'relationship',
    'primaryText': primaryText,
    'connectionSummary': primaryText,
    'primarySpans': <Map<String, Object?>>[
      <String, Object?>{
        'text': '林清越',
        'role': 'object',
        'target': personTarget,
      },
      <String, Object?>{'text': '也看过「', 'role': 'plain'},
      <String, Object?>{
        'text': objectText,
        'role': 'object',
        'target': objectTarget,
      },
      <String, Object?>{'text': '」', 'role': 'plain'},
    ],
    'intersectionPoints': <Map<String, Object?>>[
      <String, Object?>{
        'pointId': 'ix_lm_${index + 1}_p0',
        'pointClass': 'fact',
        'dimension': index.isEven ? 'location' : 'relationship',
        'label': '关注的人也看过',
        'displayText': primaryText,
        'sourceRef': 'relationship',
        'visibility': 'public',
        'count': index + 1,
        'sampleText': '林清越',
      },
    ],
    'freshAgoHours': index + 1,
    'actorEvidenceTotalCount': 1,
    'actorEvidenceCompleteness': 'complete',
    'actorEvidence': <Map<String, Object?>>[
      <String, Object?>{
        'actorId': 'fixture_user_lin',
        'displayName': '林清越',
        'relationLabel': '关注你的人',
        'relationSourceRef': 'relationship',
        'sourcePointId': 'ix_lm_${index + 1}_actor_1',
        'sourceRef': 'relationship',
        'actionSummaryText': '也看过「$objectText」',
        'privacyState': 'visible',
        'target': personTarget,
        'evidenceRank': 1,
        'snapshotVersion': 'snap_ix_lm_${index + 1}',
        'sortKey': 1,
      },
    ],
    'representativeActor': <String, Object?>{
      'actorId': 'fixture_user_lin',
      'displayName': '林清越',
      'relationLabel': '关注你的人',
      'privacyState': 'visible',
      'target': personTarget,
      'evidenceRank': 1,
      'snapshotVersion': 'snap_ix_lm_${index + 1}',
    },
    'lifecycleState': lifecycle,
    'strength': 0.8,
    'previousStrength': 0.7,
    'strengthDelta': 0.1,
  };
}

Map<String, Object?> _authorImpact(String authorId) {
  const helpTypes = <String>[
    'community',
    'decision',
    'spread',
    'relationship',
    'knowledge',
  ];
  const dimensions = <String>[
    'interest',
    'location',
    'content',
    'relationship',
    'content',
  ];
  final items = List<Map<String, Object?>>.generate(helpTypes.length, (index) {
    final primaryText = '林清越等${index + 3}人因你的内容获得帮助';
    return <String, Object?>{
      'impactId': 'impact_${authorId}_$index',
      'helpType': helpTypes[index],
      'action': 'view',
      'intersectionDimension': dimensions[index],
      'tagRef': 'tag/fixture/${helpTypes[index]}',
      'source': 'content',
      'count': index + 3,
      'primaryText': primaryText,
      'subtitleText': '固定 seed 影响证据',
      'countObjectKind': 'person',
      'evidenceSnapshotId': 'impact_snapshot_${authorId}_$index',
      'iconKey': 'content',
      'freshAt': '2026-07-20T00:00:00Z',
      'timeBucket': 'today',
      'lifecycleState': index.isEven ? 'strengthened' : 'reactivated',
      'previousStrength': 0.7,
      'strengthDelta': 0.1,
      'primarySpans': <Map<String, Object?>>[
        <String, Object?>{'text': primaryText, 'role': 'plain'},
      ],
      'representativeActor': <String, Object?>{
        'actorId': 'fixture_user_lin',
        'displayName': '林清越',
        'relationLabel': '读者',
        'privacyState': 'visible',
        'target': _target('user', 'fixture_user_lin', 'person', 'userProfile'),
        'evidenceRank': 1,
        'snapshotVersion': 'impact_snapshot_${authorId}_$index',
      },
    };
  }, growable: false);
  return <String, Object?>{
    'authorId': authorId,
    'total': items.length,
    'items': items,
  };
}

List<Map<String, Object?>> _profileShareInteractions() {
  const states = <String>[
    'active',
    'active',
    'active',
    'deleted',
    'private',
    'reviewing',
    'author_deactivated',
  ];
  return List<Map<String, Object?>>.generate(states.length, (index) {
    final received = index != 1;
    return <String, Object?>{
      'interactionId': 'share_fixture_${index + 1}',
      'activityType': 'share',
      'direction': received ? 'received' : 'sent',
      'ownerPersonaId': 'fixture_user_current',
      'actorPersonaId': received
          ? 'fixture_user_friend'
          : 'fixture_user_current',
      'actorDisplayName': received ? '林清越' : '新同学_260622_6698692',
      'targetPersonaId': received
          ? 'fixture_user_current'
          : 'fixture_user_photo',
      'targetContentId': _contentPostIds[index % _contentPostIds.length],
      'targetKind': index == 2 ? 'discussion' : 'record',
      'targetAvailability': states[index],
      'previewMediaKind': states[index] == 'active'
          ? (index == 0 ? 'video' : 'image')
          : 'none',
      'previewImageUrl': states[index] == 'active'
          ? 'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png'
          : '',
      'occurredAt': '2026-07-${12 - index}T08:10:00Z',
    };
  }, growable: false);
}

Map<String, Object?> _userDocument() {
  final identities = <(String, String)>[
    ('fixture_user_current', '新同学_260622_6698692'),
    ('fixture_user_photo', '契约摄影师'),
    ('fixture_user_travel', '契约旅行家'),
    ('fixture_user_article', '契约撰稿人'),
    ('fixture_user_friend', '契约好友'),
    ('fixture_user_weekend_1', '契约同伴一'),
    ('fixture_user_weekend_2', '契约同伴二'),
    ('nature_photographer', '自然摄影师'),
  ];
  return <String, Object?>{
    'examples': <String, Object?>{
      'user_profile_core': <String, Object?>{
        'profiles': identities
            .map((identity) => _profile(identity.$1, identity.$2))
            .toList(growable: false),
      },
      'profile_feed_core': <String, Object?>{
        'myPostIds': <String>[
          'fixture_moment_001',
          'fixture_moment_002',
          'fixture_moment_003',
          'fixture_post_lifestyle_001',
        ],
        'authorPostIds': <String>[
          'fixture_photo_001',
          'fixture_photo_002',
          'fixture_post_photography_001',
        ],
        'commentIds': <String>['fixture_comment_fixture_photo_002'],
      },
      'relationship_core': <String, Object?>{
        'relationships':
            <String>[
                  'fixture_user_photo',
                  'fixture_user_friend',
                  'fixture_user_weekend_1',
                ]
                .map(
                  (target) => <String, Object?>{
                    'sourceUserId': 'fixture_user_current',
                    'targetUserId': target,
                    'following': true,
                    'mutualFollow': true,
                    'blocked': false,
                    'canChat': true,
                    'canCall': true,
                  },
                )
                .toList(growable: false),
      },
      'following_subject_core': <String, Object?>{
        'items': <Map<String, Object?>>[
          _followingSubject(
            'user_travel_photographer',
            'persona',
            '旅行摄影师',
            true,
          ),
          _followingSubject('circle_sichuan_travel', 'circle', '四川旅行圈', false),
          _followingSubject('homepage_sight_emeishan', 'homepage', '峨眉山', true),
        ],
      },
    },
  };
}

Map<String, Object?> _profile(String userId, String displayName) =>
    <String, Object?>{
      'userId': userId,
      'personaId': userId,
      'ownerUserId': userId,
      'userHandle': userId,
      'displayName': displayName,
      'avatarUrl': _avatar(userId),
      'avatarObjectKey': _avatar(userId),
      'backgroundUrl': _background(userId),
      'backgroundObjectKey': _background(userId),
      'bio': userId == 'fixture_user_current' ? '' : '固定 seed 用户档案。',
      'primaryRole': userId == 'fixture_user_current'
          ? 'currentUserVariant'
          : 'leadAuthor',
      'avatarVersion': 1,
      'followerCount': 240,
      'followingCount': 96,
      'postCount': 8,
      'circleCount': 5,
      'likeCount': 360,
      'stats': <String, Object?>{
        'followingCount': 96,
        'followerCount': 240,
        'postCount': 8,
        'circleCount': 5,
        'likeCount': 360,
      },
      'personaRefs': userId == 'fixture_user_current'
          ? <String>['fixture_persona_daily', 'fixture_persona_work']
          : <String>[],
      'tags': <String>['fixture', 'contact'],
      'identityTags': <String>[],
    };

Map<String, Object?> _followingSubject(
  String id,
  String type,
  String name,
  bool unread,
) => <String, Object?>{
  'subjectId': id,
  'subjectType': type,
  'displayName': name,
  'avatarUrl': type == 'persona' ? _avatar('fixture_user_photo') : '',
  'coverUrl': type == 'persona'
      ? ''
      : 'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
  'subtitle': '固定 seed 动态',
  'targetRouteId': '${type}_detail',
  'targetObjectId': id,
  'followedAt': '2026-05-20T08:00:00Z',
  'lastVisitedAt': '2026-06-01T08:00:00Z',
  'latestChangedAt': '2026-06-02T00:30:00Z',
  'unreadChangeCount': unread ? 1 : 0,
  'hasUnreadChanges': unread,
  'latestChangeReason': unread ? '发布了新内容' : '',
};

Map<String, Object?> _chatDocument() {
  final specs = <(String, String, String, List<String>)>[
    (
      'fixture_conv_direct',
      'direct',
      '契约好友',
      <String>['fixture_user_current', 'fixture_user_friend'],
    ),
    (
      'fixture_conv_group',
      'group',
      '契约周末群',
      <String>[
        'fixture_user_current',
        'fixture_user_weekend_1',
        'fixture_user_weekend_2',
      ],
    ),
    (
      'fixture_conv_photo_group',
      'group',
      '契约摄影交流群',
      <String>[
        'fixture_user_current',
        'fixture_user_photo',
        'fixture_user_friend',
      ],
    ),
    (
      'fixture_conv_article_direct',
      'direct',
      '契约撰稿人',
      <String>['fixture_user_current', 'fixture_user_article'],
    ),
    (
      'conv_001',
      'direct',
      '契约联系人',
      <String>['fixture_user_current', 'fixture_user_friend'],
    ),
  ];
  final conversations = <Map<String, Object?>>[];
  final messages = <String, Object?>{};
  final members = <String, Object?>{};
  final states = <Map<String, Object?>>[];
  for (var index = 0; index < specs.length; index++) {
    final spec = specs[index];
    final count = spec.$2 == 'group' ? 8 : 6;
    conversations.add(
      _conversation(spec.$1, spec.$2, spec.$3, spec.$4, count, index),
    );
    messages[spec.$1] = List<Map<String, Object?>>.generate(
      count,
      (messageIndex) => _message(spec.$1, spec.$4, messageIndex),
      growable: false,
    );
    members[spec.$1] = spec.$4
        .map(
          (userId) => <String, Object?>{
            'userId': userId,
            'displayName': _displayName(userId),
            'avatarUrl': _avatar(userId),
            'userHandle': userId,
            'role': userId == spec.$4.first ? 'owner' : 'member',
            'isCurrentUser': userId == 'fixture_user_current',
          },
        )
        .toList(growable: false);
    states.add(<String, Object?>{
      'id': 'fixture_state_${spec.$1}',
      'userId': 'fixture_user_current',
      'conversationId': spec.$1,
      'readSeq': count - 1,
      'unreadCount': 1,
      'mentionUnreadCount': index == 0 ? 1 : 0,
      'muted': false,
      'pinned': index == 0,
      'updatedAt': '2026-06-10T10:00:00Z',
    });
  }
  final contactIds = <String>[
    'fixture_user_friend',
    'fixture_user_weekend_1',
    'fixture_user_weekend_2',
    'fixture_user_photo',
    'fixture_user_travel',
    'fixture_user_article',
  ];
  return <String, Object?>{
    'examples': <String, Object?>{
      'chat_core': <String, Object?>{
        'currentUserId': 'fixture_user_current',
        'conversations': conversations,
        'messages': messages,
        'members': members,
        'userStates': states,
      },
      'chat_contacts_core': <String, Object?>{
        'contacts': contactIds
            .map(
              (id) => <String, Object?>{
                'userId': id,
                'displayName': _displayName(id),
                'avatarUrl': _avatar(id),
                'avatarObjectKey': _avatar(id),
                'userHandle': id,
                'relationState': 'mutual',
                'source': 'follow',
                'bio': '固定 seed 联系人。',
              },
            )
            .toList(growable: false),
        'circleIds': <String>[
          'fixture_circle_photo',
          'fixture_circle_travel',
          'fixture_circle_life',
        ],
        'groupConversationIds': <String>[
          'fixture_conv_group',
          'fixture_conv_photo_group',
        ],
      },
      'chat_settings_core': <String, Object?>{
        'settings': <Map<String, Object?>>[
          <String, Object?>{
            'conversationId': 'fixture_conv_group',
            'muted': false,
            'pinned': false,
            'announcement': '契约群公告：周末集合时间已确认',
            'adminUserIds': <String>['fixture_user_weekend_1'],
            'transferCandidateUserIds': <String>[
              'fixture_user_weekend_1',
              'fixture_user_weekend_2',
            ],
          },
        ],
      },
      'chat_group_flow_core': <String, Object?>{
        'candidateUserIds': <String>[
          'fixture_user_friend',
          'fixture_user_weekend_1',
          'fixture_user_weekend_2',
        ],
        'defaultGroupTitle': '契约新建群',
      },
      'chat_realtime_fixture_core': <String, Object?>{
        'realtimeEvents': <String, Object?>{
          'conv_001': <Map<String, Object?>>[
            <String, Object?>{
              'type': 'MessageSent',
              'conversationId': 'conv_001',
              'payload': _message('conv_001', <String>[
                'fixture_user_friend',
              ], 12),
            },
          ],
          'fixture_conv_group': <Map<String, Object?>>[
            <String, Object?>{
              'type': 'ConversationMemberAdded',
              'conversationId': 'fixture_conv_group',
              'payload': <String, Object?>{'userId': 'fixture_user_weekend_2'},
            },
          ],
        },
      },
    },
  };
}

Map<String, Object?> _conversation(
  String id,
  String type,
  String title,
  List<String> userIds,
  int messageCount,
  int index,
) => <String, Object?>{
  'id': id,
  'type': type,
  'conversationType': type == 'group'
      ? 'interestGroupConversation'
      : 'directConversation',
  'title': title,
  'avatarUrl': type == 'group'
      ? 'media/avatar/s/archived-avatar/group/$id/v1/composite.png'
      : _avatar(userIds.last),
  'avatarObjectKey': type == 'group'
      ? 'media/avatar/s/archived-avatar/group/$id/v1/composite.png'
      : _avatar(userIds.last),
  'creatorId': userIds.first,
  'maxSeq': messageCount,
  'memberCount': userIds.length,
  'maxGroupSize': type == 'group' ? 500 : 2,
  'receiptEnabled': true,
  'lastMessagePreview': '$title 固定 seed 消息 #$messageCount',
  'lastMessageTime': '2026-06-10T1${index}:00:00Z',
  'messageCount': messageCount,
  'status': 'active',
  'createdAt': '2026-06-10T0${index}:00:00Z',
  'updatedAt': '2026-06-10T1${index}:00:00Z',
  if (type == 'group') 'groupAvatarVersion': 1,
  if (type == 'group') 'groupAvatarSourceUserIds': userIds,
  if (id == 'fixture_conv_photo_group') 'circleId': 'fixture_circle_photo',
  if (type == 'direct') 'targetUserId': userIds.last,
};

Map<String, Object?> _message(
  String conversationId,
  List<String> userIds,
  int index,
) {
  final seq = index + 1;
  final sender = userIds[index % userIds.length];
  final type = conversationId == 'fixture_conv_direct' && index == 2
      ? 'image'
      : conversationId == 'fixture_conv_direct' && index == 3
      ? 'video'
      : conversationId == 'fixture_conv_direct' && index == 4
      ? 'file'
      : 'text';
  final id = conversationId == 'fixture_conv_direct'
      ? <String>[
          'fixture_msg_direct_1',
          'fixture_msg_direct_2',
          'fixture_msg_direct_image_1',
          'fixture_msg_direct_video_1',
          'fixture_msg_direct_file_1',
          'fixture_conv_direct_msg_06',
        ][index]
      : 'fixture_msg_${conversationId}_$seq';
  return <String, Object?>{
    'id': id,
    'conversationId': conversationId,
    'seq': seq,
    'clientMsgId': '${id}_client',
    'senderId': sender,
    'senderName': _displayName(sender),
    'senderAvatar': _avatar(sender),
    'content': '$conversationId 固定 seed 消息 #$seq',
    'type': type,
    'status': 'sent',
    'timestamp': DateTime.utc(
      2026,
      6,
      10,
    ).add(Duration(minutes: index)).toIso8601String(),
    if (type != 'text')
      'mediaDeliveryUrl': type == 'video'
          ? 'media/video/s/archived-video/post/fixture_video_001/v1/video.mp4'
          : type == 'file'
          ? 'media/attachment/s/archived-attachment/post/fixture_chat_file_001/v1/spec.txt'
          : 'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
    if (type != 'text') 'mediaType': type,
    if (type != 'text')
      'mediaContentType': type == 'video'
          ? 'video/mp4'
          : type == 'file'
          ? 'text/plain'
          : 'image/png',
  };
}

Map<String, Object?> _target(
  String objectType,
  String objectId,
  String objectKind,
  String routeId,
) => <String, Object?>{
  'objectType': objectType,
  'objectId': objectId,
  'objectKind': objectKind,
  'routeId': routeId,
};

Map<String, Object?> _stringMap(Map<Object?, Object?> source) =>
    source.map((key, value) => MapEntry(key.toString(), value));

String _avatar(String userId) =>
    'media/avatar/s/archived-avatar/user/$userId/v1/avatar.png';

String _background(String userId) =>
    'media/background/s/archived-avatar/user/$userId/v1/background.png';

String _displayName(String userId) =>
    <String, String>{
      'fixture_user_current': '新同学_260622_6698692',
      'fixture_user_friend': '契约好友',
      'fixture_user_weekend_1': '契约同伴一',
      'fixture_user_weekend_2': '契约同伴二',
      'fixture_user_photo': '契约摄影师',
      'fixture_user_travel': '契约旅行家',
      'fixture_user_article': '契约撰稿人',
    }[userId] ??
    userId;
