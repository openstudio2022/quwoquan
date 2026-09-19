import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';

/// Alpha 本地演练的 Post 交集投影 seam。
///
/// 输入只来自当前 viewer 的关系事实、其他 persona 的内容行为事实与当前
/// canonical Post 投影；不读取测试 fixture，也不把私有 viewer 事实写回公共 bundle。
final class AlphaPostIntersectionProjector {
  const AlphaPostIntersectionProjector();

  Map<String, Object?> project({
    required Map<String, Object?> post,
    required String viewerId,
    required AlphaRehearsalStore store,
    required DateTime now,
  }) {
    final postId = '${post['postId'] ?? ''}'.trim();
    final viewer = viewerId.trim();
    if (postId.isEmpty || viewer.isEmpty) {
      return Map<String, Object?>.from(post);
    }
    final followed = store.followingOf(viewer).toSet();
    final actors =
        store.reactions.values
            .where((row) => row['postId'] == postId && row['liked'] == true)
            .map((row) => '${row['actorId'] ?? ''}'.trim())
            .where(
              (actor) =>
                  actor.isNotEmpty &&
                  actor != viewer &&
                  followed.contains(actor),
            )
            .toList(growable: false)
          ..sort();
    if (actors.isEmpty) return Map<String, Object?>.from(post);

    final actor = actors.first;
    final title = '${post['title'] ?? post['summary'] ?? ''}'.trim();
    if (title.isEmpty) return Map<String, Object?>.from(post);
    final actorName = _displayName(store, actor);
    final objectText = '《$title》';
    final primaryText = '$actorName也赞过$objectText';
    final freshAt = now.toUtc();
    final target = <String, Object?>{
      'objectType': 'post',
      'objectId': postId,
      'objectKind': 'content',
      'routeId': 'workBrowser',
    };
    final reason = <String, Object?>{
      'kind': 'coLiked',
      'vertical': 'general',
      'dimension': 'content',
      'tagRefs': const <Object>[],
      'relationKind': 'following',
      'objectKind': 'content',
      'relationObjectId': postId,
      'strength': 1.0,
      'primaryText': primaryText,
      'primaryTextL10nKey': 'intersection.coLiked.named',
      'displayBinding': 'explicit_link',
      'secondaryText': '',
      'weightTier': 'light',
      'actionType': 'open_content',
      'actionTargetId': postId,
      'source': 'alpha_rehearsal_relationship_behavior_projection',
      'intersectionId': 'alpha:$viewer:$actor:$postId:coLiked',
      'intersectionClass': 'fact',
      'avatarUrl': '',
      'displayName': title,
      'confidenceLabel': '',
      'modelReasonBucket': '',
      'freshAt': freshAt.toIso8601String(),
      'expiresAt': freshAt.add(const Duration(days: 7)).toIso8601String(),
      'intersectionPoints': <Object>[
        <String, Object?>{
          'pointId': 'alpha:$actor:$postId:like',
          'pointClass': 'fact',
          'dimension': 'content',
          'label': '共同喜欢',
          'displayText': '$actorName赞过该作品',
          'sourceRef': 'content-reaction:$actor:$postId',
          'visibility': 'visible',
          'count': 1,
          'sampleText': '',
          'sampleAvatarUrls': const <Object>[],
          'sampleVisuals': const <Object>[],
        },
      ],
      'pointSummarySnapshotId': 'alpha:$viewer:$postId',
      'cohort': 'alpha-rehearsal-v1',
      'actorEvidenceTotalCount': 1,
      'actorEvidenceCompleteness': 'complete',
      'actorEvidence': const <Object>[],
      'factPointCount': 1,
      'recommendedPointCount': 0,
      'totalPointCount': 1,
      'dimensionPointSummary': const <Object>[],
      'pointClassLabel': '事实交集',
      'connectionSummary': '',
      'lastRecommendedAt': '',
      'seenAt': '',
      'rankState': 'eligible',
      'primarySpans': <Object>[
        <String, Object?>{'text': '$actorName也赞过', 'role': 'plain'},
        <String, Object?>{
          'text': objectText,
          'role': 'object',
          'target': target,
        },
      ],
      'sampleVisuals': const <Object>[],
      'representativeActor': <String, Object?>{
        'actorId': actor,
        'displayName': actorName,
        'avatarUrl': '',
        'relationLabel': '关注的人',
        'privacyState': 'visible',
        'target': <String, Object?>{
          'objectType': 'user',
          'objectId': actor,
          'objectKind': 'person',
          'routeId': 'userProfile',
        },
        'evidenceRank': 1,
        'snapshotVersion': '1',
      },
      'actionHints': const <Object>[],
      'evidenceRows': <Object>[
        <String, Object?>{
          'text': '$actorName赞过该作品',
          'source': 'content_reaction',
        },
      ],
      'lifecycleState': 'new',
      'previousStrength': 0.0,
      'strengthDelta': 1.0,
      'edgeWeight': 1.0,
      'iconKey': 'content',
      'tone': 'positive',
      'timeBucket': 'recent',
      'dedupeKey': 'coLiked:$actor:$postId',
      'anchorUserWeight': 1.0,
      'mutualCount': 1,
      'moment': 'discovery',
      'subjectId': viewer,
      'subjectContext': 'post:$postId',
    };
    return <String, Object?>{
      ...post,
      'intersectionReasons': <Object>[reason],
    };
  }

  String _displayName(AlphaRehearsalStore store, String personaId) {
    for (final row in store.identities.values) {
      if (row['personaId'] == personaId) {
        final name = '${row['displayName'] ?? ''}'.trim();
        if (name.isNotEmpty) return name;
      }
    }
    return personaId;
  }
}
