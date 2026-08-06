import 'dart:convert' show utf8;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../runtime/fixtures/object_scenario_seed_reader.dart';

/// Alpha/test 的 ProfileInteraction typed Facet。
///
/// 数据只来自 metadata seed manifest 生成的 immutable bundle；seen/read 事实按
/// owner+activity+state 语义键在 alpha 进程内幂等追加。
final class InMemoryProfileInteractionFacet
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  InMemoryProfileInteractionFacet({DateTime Function()? clock})
    : _clock = clock ?? (() => DateTime.now().toUtc()),
      _rows = _loadRows();

  final DateTime Function() _clock;
  final List<_InMemoryProfileActivityRow> _rows;
  final Map<String, ProfileInteractionReadFactAck> _facts =
      <String, ProfileInteractionReadFactAck>{};

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) async {
    final matching =
        _rows
            .where(
              (row) =>
                  row.ownerPersonaId == query.personaId &&
                  row.activity.direction == direction &&
                  row.activity.activityType == query.type,
            )
            .toList(growable: false)
          ..sort(
            (left, right) =>
                right.activity.occurredAt.compareTo(left.activity.occurredAt),
          );
    var start = 0;
    final cursor = query.cursor?.trim() ?? '';
    if (cursor.isNotEmpty) {
      final index = matching.indexWhere(
        (row) => row.activity.activityId == cursor,
      );
      if (index < 0) {
        throw const FormatException('profile interaction cursor is invalid');
      }
      start = index + 1;
    }
    final end = (start + query.limit).clamp(0, matching.length);
    final page = start >= matching.length
        ? const <_InMemoryProfileActivityRow>[]
        : matching.sublist(start, end);
    return ProfileInteractionActivityPageSlice(
      items: List<ProfileInteractionActivityView>.unmodifiable(
        page.map((row) => row.activity),
      ),
      nextCursor: end < matching.length && page.isNotEmpty
          ? page.last.activity.activityId
          : null,
      hasMore: end < matching.length,
    );
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    final rowIndex = _rows.indexWhere(
      (row) =>
          row.ownerPersonaId == command.personaId &&
          row.activity.direction == InteractionDirection.received &&
          row.activity.activityId == command.activityId,
    );
    if (rowIndex < 0) {
      throw StateError('profile interaction activity is not owned by persona');
    }
    final semanticKey =
        '${command.personaId}\u0000${command.activityId}\u0000'
        '${command.state.wireName}';
    final replay = _facts[semanticKey];
    if (replay != null) {
      return ProfileInteractionReadFactAck(
        factId: replay.factId,
        activityId: replay.activityId,
        state: replay.state,
        occurredAt: replay.occurredAt,
        replayed: true,
      );
    }
    final occurredAt = _clock();
    final factId =
        'pirf_${sha256.convert(utf8.encode(semanticKey)).toString().substring(0, 32)}';
    final ack = ProfileInteractionReadFactAck(
      factId: factId,
      activityId: command.activityId,
      state: command.state,
      occurredAt: occurredAt,
      replayed: false,
    );
    _facts[semanticKey] = ack;
    final row = _rows[rowIndex];
    _rows[rowIndex] = _InMemoryProfileActivityRow(
      ownerPersonaId: row.ownerPersonaId,
      activity: _withReadState(
        row.activity,
        state: command.state,
        occurredAt: occurredAt,
      ),
    );
    return ack;
  }

  static List<_InMemoryProfileActivityRow> _loadRows() {
    final root = objectScenarioSeedReader.document('content');
    if (root['seedSets'] is! Map) {
      throw const FormatException('content fixture seedSets are missing');
    }
    final seed = (root['seedSets'] as Map)['profile_share_interaction_core'];
    if (seed is! Map || seed['profileShareInteractions'] is! List) {
      return <_InMemoryProfileActivityRow>[];
    }
    return (seed['profileShareInteractions'] as List)
        .whereType<Map>()
        .map(_decodeRow)
        .toList(growable: true);
  }

  static _InMemoryProfileActivityRow _decodeRow(Map<dynamic, dynamic> raw) {
    final occurredAt = _requiredDateTime(raw['occurredAt'], 'occurredAt');
    final direction = _text(raw['direction'], fallback: 'received');
    final activityID = _requiredText(raw['interactionId'], 'interactionId');
    final ownerPersonaID = _requiredText(
      raw['ownerPersonaId'],
      'ownerPersonaId',
    );
    final actorID = _requiredText(raw['actorPersonaId'], 'actorPersonaId');
    final targetPersonaID = _requiredText(
      raw['targetPersonaId'],
      'targetPersonaId',
    );
    final counterpartID = _text(raw['counterpartPersonaId']);
    final actorName = _text(raw['actorDisplayName'], fallback: actorID);
    final counterpartName = _text(
      raw['counterpartDisplayName'],
      fallback: counterpartID,
    );
    final displayID = direction == 'sent' && counterpartID.isNotEmpty
        ? counterpartID
        : actorID;
    final displayName = direction == 'sent' && counterpartName.isNotEmpty
        ? counterpartName
        : actorName;
    final availability = _text(raw['targetAvailability'], fallback: 'active');
    final previewKind = _text(raw['previewMediaKind'], fallback: 'none');
    final targetKind = _text(raw['targetKind'], fallback: 'record');
    final targetContentID = _requiredText(
      raw['targetContentId'],
      'targetContentId',
    );
    return _InMemoryProfileActivityRow(
      ownerPersonaId: ownerPersonaID,
      activity: ProfileInteractionActivityView(
        ownerPersonaId: ownerPersonaID,
        activityId: activityID,
        activityType: InteractionActivityType.fromWire(
          _text(raw['activityType'], fallback: 'share'),
          'profileShareInteractions.activityType',
        ),
        direction: InteractionDirection.fromWire(
          direction,
          'profileShareInteractions.direction',
        ),
        sourceType: 'profile_share_interaction_seed',
        sourceEventId: activityID,
        sourceVersion: 1,
        viewerReactionVersion: 0,
        targetVersion: 0,
        active: true,
        commentKind: 'none',
        viewerReaction: CommentReactionType.none,
        actorPersonaId: actorID,
        actorDisplayName: actorName,
        actorAvatarUrl: _text(raw['actorAvatarUrl']),
        actorAvatarVersion: 0,
        counterpartPersonaId: counterpartID,
        counterpartDisplayName: counterpartName,
        counterpartAvatarUrl: _text(raw['counterpartAvatarUrl']),
        targetPersonaId: targetPersonaID,
        targetContentId: targetContentID,
        targetContentType: switch (previewKind) {
          'video' => ContentType.video,
          'image' => ContentType.image,
          _ =>
            targetKind == 'discussion'
                ? ContentType.micro
                : ContentType.article,
        },
        targetContentSummary: _text(raw['targetContentSummary']),
        targetKind: targetKind,
        targetAvailability: availability,
        targetReplyCount: _integer(raw['targetReplyCount']),
        displayPersonaId: displayID,
        displayName: displayName,
        displayAvatarUrl: direction == 'sent'
            ? _text(raw['counterpartAvatarUrl'])
            : _text(raw['actorAvatarUrl']),
        displayAvatarVersion: 0,
        displayUserRouteId: 'userProfile',
        primaryText: direction == 'sent' ? '你转发了TA的记录' : '转发了你的记录',
        contextText: _text(raw['shareText']),
        previewMediaKind: previewKind,
        previewImageUrl: _text(raw['previewImageUrl']),
        previewText: _text(raw['targetContentSummary']),
        previewUnavailable: availability != 'active',
        previewObjectId: targetContentID,
        previewRouteId: availability == 'active' ? 'workBrowser' : '',
        outboundShareEventId: activityID,
        shareText: _text(raw['shareText']),
        impactPrimaryText: _text(raw['impactPrimaryText']),
        impactDeepLink: _text(raw['impactDeepLink']),
        filterKeys: const <String>['shares'],
        createdAt: occurredAt,
        occurredAt: occurredAt,
        seenAt: _dateTime(raw['seenAt']),
        readAt: _dateTime(raw['readAt']),
      ),
    );
  }
}

final class _InMemoryProfileActivityRow {
  const _InMemoryProfileActivityRow({
    required this.ownerPersonaId,
    required this.activity,
  });

  final String ownerPersonaId;
  final ProfileInteractionActivityView activity;
}

ProfileInteractionActivityView _withReadState(
  ProfileInteractionActivityView activity, {
  required ProfileInteractionReadState state,
  required DateTime occurredAt,
}) {
  return ProfileInteractionActivityView(
    ownerPersonaId: activity.ownerPersonaId,
    activityId: activity.activityId,
    activityType: activity.activityType,
    direction: activity.direction,
    sourceType: activity.sourceType,
    sourceEventId: activity.sourceEventId,
    sourceVersion: activity.sourceVersion,
    viewerReactionVersion: activity.viewerReactionVersion,
    targetVersion: activity.targetVersion,
    active: activity.active,
    commentKind: activity.commentKind,
    commentId: activity.commentId,
    parentCommentId: activity.parentCommentId,
    viewerReaction: activity.viewerReaction,
    actorPersonaId: activity.actorPersonaId,
    actorDisplayName: activity.actorDisplayName,
    actorAvatarUrl: activity.actorAvatarUrl,
    actorAvatarVersion: activity.actorAvatarVersion,
    counterpartPersonaId: activity.counterpartPersonaId,
    counterpartDisplayName: activity.counterpartDisplayName,
    counterpartAvatarUrl: activity.counterpartAvatarUrl,
    targetPersonaId: activity.targetPersonaId,
    targetContentId: activity.targetContentId,
    targetContentType: activity.targetContentType,
    targetContentSummary: activity.targetContentSummary,
    targetKind: activity.targetKind,
    targetAvailability: activity.targetAvailability,
    targetReplyCount: activity.targetReplyCount,
    displayPersonaId: activity.displayPersonaId,
    displayName: activity.displayName,
    displayAvatarUrl: activity.displayAvatarUrl,
    displayAvatarVersion: activity.displayAvatarVersion,
    displayUserRouteId: activity.displayUserRouteId,
    primaryText: activity.primaryText,
    contextText: activity.contextText,
    previewMediaKind: activity.previewMediaKind,
    previewImageUrl: activity.previewImageUrl,
    previewText: activity.previewText,
    previewUnavailable: activity.previewUnavailable,
    previewObjectId: activity.previewObjectId,
    previewRouteId: activity.previewRouteId,
    outboundShareEventId: activity.outboundShareEventId,
    shareText: activity.shareText,
    impactPrimaryText: activity.impactPrimaryText,
    impactDeepLink: activity.impactDeepLink,
    filterKeys: activity.filterKeys,
    createdAt: activity.createdAt,
    occurredAt: activity.occurredAt,
    seenAt: activity.seenAt ?? occurredAt,
    readAt: state == ProfileInteractionReadState.read
        ? (activity.readAt ?? occurredAt)
        : activity.readAt,
  );
}

String _text(Object? value, {String fallback = ''}) {
  final text = value?.toString().trim() ?? '';
  return text.isEmpty ? fallback : text;
}

String _requiredText(Object? value, String name) {
  final text = _text(value);
  if (text.isEmpty) {
    throw FormatException('$name must be a non-empty string');
  }
  return text;
}

int _integer(Object? value) {
  if (value is num) {
    return value.toInt();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

DateTime? _dateTime(Object? value) {
  final text = _text(value);
  return text.isEmpty ? null : DateTime.tryParse(text)?.toUtc();
}

DateTime _requiredDateTime(Object? value, String name) {
  final parsed = _dateTime(value);
  if (parsed == null) {
    throw FormatException('$name must be an ISO-8601 timestamp');
  }
  return parsed;
}
