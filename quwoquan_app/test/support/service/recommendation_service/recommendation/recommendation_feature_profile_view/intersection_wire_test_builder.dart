/// recommendation_feature_profile_view 自己的固定交集 wire。
///
/// 只覆盖该对象 local_contract 所需的生命周期、objectKind 与 impact 边界。
Map<String, Object?> intersectionWireExample() {
  const kinds = <String>[
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
    kinds.length,
    (index) => _intersectionReason(
      index: index,
      objectKind: kinds[index],
      lifecycle: lifecycles[index],
    ),
    growable: false,
  );
  return <String, Object?>{
    'inboxReasons': reasons,
    'objectIntersections': <String, Object?>{
      'fixture_homepage_travel_route_erhai': <Object?>[
        <String, Object?>{
          ...reasons.first,
          'intersectionId': 'objix_erhai_followee',
          'relationObjectId': 'fixture_homepage_travel_route_erhai',
          'actionTargetId': 'fixture_homepage_travel_route_erhai',
        },
      ],
      'u_lin': <Object?>[reasons[5]],
      'c_photo': <Object?>[reasons[4]],
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
  final objectId = index == 0
      ? 'fixture_homepage_travel_route_erhai'
      : 'fixture_homepage_travel_${objectKind}_$index';
  final objectText = '旅行对象${index + 1}';
  final primaryText = '林清越也看过「$objectText」';
  final dimension = <String>[
    'location',
    'relationship',
    'interest',
    'identity',
    'content',
    'location',
    'relationship',
  ][index];
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
    'dimension': dimension,
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
      const <String, Object?>{'text': '也看过「', 'role': 'plain'},
      <String, Object?>{
        'text': objectText,
        'role': 'object',
        'target': objectTarget,
      },
      const <String, Object?>{'text': '」', 'role': 'plain'},
    ],
    'intersectionPoints': <Map<String, Object?>>[
      <String, Object?>{
        'pointId': 'ix_lm_${index + 1}_p0',
        'pointClass': 'fact',
        'dimension': dimension,
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
  final items = List<Map<String, Object?>>.generate(helpTypes.length, (index) {
    final primaryText = '林清越等${index + 3}人因你的内容获得帮助';
    return <String, Object?>{
      'impactId': 'impact_${authorId}_$index',
      'helpType': helpTypes[index],
      'action': 'view',
      'intersectionDimension': <String>[
        'interest',
        'location',
        'content',
        'relationship',
        'content',
      ][index],
      'tagRef': 'tag/fixture/${helpTypes[index]}',
      'source': 'content',
      'count': index + 3,
      'primaryText': primaryText,
      'subtitleText': '对象级影响证据',
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
