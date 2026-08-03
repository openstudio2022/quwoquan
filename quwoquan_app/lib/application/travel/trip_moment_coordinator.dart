import 'package:quwoquan_app/application/travel/trip_journey_query.dart';
import 'package:quwoquan_app/application/travel/trip_moment_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class TripMomentTarget {
  const TripMomentTarget({required this.dayIndex, required this.itemId});

  final int dayIndex;
  final String itemId;
}

/// 一次用户确认的 Moment 意图。命令与幂等键一起冻结，以便
/// 网络失败后安全重试，不会在新 Revision 上悄然重放。
final class TripMomentCreateIntent {
  const TripMomentCreateIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final CreateTripMomentRequest command;
  final String idempotencyKey;
}

final class TripMomentAssignIntent {
  const TripMomentAssignIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final AssignTripMomentRequest command;
  final String idempotencyKey;
}

final class TripMomentDeleteIntent {
  const TripMomentDeleteIntent({
    required this.command,
    required this.idempotencyKey,
  });

  final DeleteTripMomentRequest command;
  final String idempotencyKey;
}

final class TripMomentCoordinator {
  const TripMomentCoordinator({
    required this.facet,
    required this.idempotencyKeyFactory,
    this.now = DateTime.now,
  });

  final TripMomentFacet facet;
  final String Function() idempotencyKeyFactory;
  final DateTime Function() now;

  TripMomentCreateIntent prepareText({
    required TripJourneySnapshot snapshot,
    required String text,
    TripMomentTarget? target,
    TripMomentVisibility visibility = TripMomentVisibility.personal,
  }) {
    final normalizedText = text.trim();
    if (normalizedText.isEmpty) {
      throw ArgumentError('text and one current Trip revision are required');
    }
    return _prepare(
      snapshot: snapshot,
      kind: TripMomentKind.text,
      inlineText: normalizedText,
      capturedAt: now(),
      target: target,
      visibility: visibility,
      sourceVersion: 0,
    );
  }

  /// 冻结一次已经由 Content owner 确认的 MediaAsset 引用。
  ///
  /// 调用方必须先完成真实上传并读取 canonical asset version；本协调器不接受
  /// 本地路径、CDN URL 或 processing 中的临时 session，避免把可变交付地址写进
  /// TripMoment。
  TripMomentCreateIntent prepareMedia({
    required TripJourneySnapshot snapshot,
    required TripMomentKind kind,
    required String assetId,
    required int assetVersion,
    TripMomentTarget? target,
    TripMomentVisibility visibility = TripMomentVisibility.personal,
    DateTime? capturedAt,
  }) {
    if (kind != TripMomentKind.photo &&
        kind != TripMomentKind.video &&
        kind != TripMomentKind.voice) {
      throw ArgumentError('media moment kind must be photo, video, or voice');
    }
    final normalizedAssetId = assetId.trim();
    if (normalizedAssetId.isEmpty || assetVersion <= 0) {
      throw ArgumentError('canonical MediaAsset identity and version required');
    }
    return _prepare(
      snapshot: snapshot,
      kind: kind,
      contentRef: TripMomentObjectRef(
        objectTypeRef: 'content.MediaAsset',
        objectId: normalizedAssetId,
      ),
      capturedAt: capturedAt ?? now(),
      target: target,
      visibility: visibility,
      sourceVersion: assetVersion,
    );
  }

  /// 冻结一篇由 Content owner Reader 返回的公开 Post 引用。
  ///
  /// `postVersion` 不允许由列表顺序、时间戳或常量推测；缺少版本的公共投影
  /// 必须先补齐 owner contract，不能降级为裸 postId。
  TripMomentCreateIntent preparePostReference({
    required TripJourneySnapshot snapshot,
    required String postId,
    required int postVersion,
    TripMomentTarget? target,
    TripMomentVisibility visibility = TripMomentVisibility.personal,
    DateTime? capturedAt,
  }) {
    final normalizedPostId = postId.trim();
    if (normalizedPostId.isEmpty || postVersion <= 0) {
      throw ArgumentError('canonical Post identity and version required');
    }
    return _prepare(
      snapshot: snapshot,
      kind: TripMomentKind.postReference,
      contentRef: TripMomentObjectRef(
        objectTypeRef: 'content.Post',
        objectId: normalizedPostId,
      ),
      capturedAt: capturedAt ?? now(),
      target: target,
      visibility: visibility,
      sourceVersion: postVersion,
    );
  }

  Future<TripMomentSlice> create(TripMomentCreateIntent intent) {
    return facet.create(intent.command, idempotencyKey: intent.idempotencyKey);
  }

  TripMomentAssignIntent prepareAssignment({
    required TripJourneySnapshot snapshot,
    required String momentId,
    required TripMomentTarget target,
    required TripMomentVisibility visibility,
  }) {
    final moment = _currentMoment(snapshot, momentId);
    if (!_containsTarget(snapshot.timeline, target)) {
      throw ArgumentError('target is not part of the current Trip revision');
    }
    return TripMomentAssignIntent(
      command: AssignTripMomentRequest(
        tripId: snapshot.plan.tripId,
        momentId: moment.momentId,
        expectedVersion: moment.version,
        revisionNumber: snapshot.plan.currentRevisionNumber,
        dayIndex: target.dayIndex,
        itemId: target.itemId,
        visibility: visibility,
        sourceVersion: moment.sourceVersion,
      ),
      idempotencyKey: _nextIdempotencyKey(),
    );
  }

  Future<TripMomentSlice> assign(TripMomentAssignIntent intent) {
    return facet.assign(intent.command, idempotencyKey: intent.idempotencyKey);
  }

  TripMomentDeleteIntent prepareDelete({
    required TripJourneySnapshot snapshot,
    required String momentId,
    required String reason,
  }) {
    final moment = _currentMoment(snapshot, momentId);
    final normalizedReason = reason.trim();
    if (normalizedReason.isEmpty) {
      throw ArgumentError('TripMoment deletion reason is required');
    }
    return TripMomentDeleteIntent(
      command: DeleteTripMomentRequest(
        tripId: snapshot.plan.tripId,
        momentId: moment.momentId,
        expectedVersion: moment.version,
        reason: normalizedReason,
      ),
      idempotencyKey: _nextIdempotencyKey(),
    );
  }

  Future<TripMomentSlice> delete(TripMomentDeleteIntent intent) {
    return facet.delete(intent.command, idempotencyKey: intent.idempotencyKey);
  }

  TripMomentCreateIntent _prepare({
    required TripJourneySnapshot snapshot,
    required TripMomentKind kind,
    required DateTime capturedAt,
    required TripMomentTarget? target,
    required TripMomentVisibility visibility,
    required int sourceVersion,
    TripMomentObjectRef? contentRef,
    String? inlineText,
  }) {
    if (!snapshot.usesOneCurrentRevision || capturedAt.toUtc().year <= 0) {
      throw ArgumentError('one current Trip revision and capturedAt required');
    }
    if (target == null && visibility != TripMomentVisibility.personal) {
      throw ArgumentError('unassigned moments must remain personal');
    }
    if (target != null && !_containsTarget(snapshot.timeline, target)) {
      throw ArgumentError('target is not part of the current Trip revision');
    }
    return TripMomentCreateIntent(
      command: CreateTripMomentRequest(
        tripId: snapshot.plan.tripId,
        revisionNumber: snapshot.plan.currentRevisionNumber,
        dayIndex: target?.dayIndex,
        itemId: target?.itemId,
        kind: kind,
        contentRef: contentRef,
        inlineText: inlineText,
        capturedAt: capturedAt.toUtc(),
        visibility: visibility,
        assignmentStatus: target == null
            ? TripMomentAssignmentStatus.unassigned
            : TripMomentAssignmentStatus.confirmed,
        sourceVersion: sourceVersion,
      ),
      idempotencyKey: _nextIdempotencyKey(),
    );
  }

  TripMomentSlice _currentMoment(
    TripJourneySnapshot snapshot,
    String momentId,
  ) {
    final normalizedMomentId = momentId.trim();
    if (!snapshot.usesOneCurrentRevision || normalizedMomentId.isEmpty) {
      throw ArgumentError('one current Trip revision and momentId required');
    }
    final matches = snapshot.moments.moments
        .where(
          (moment) =>
              moment.momentId == normalizedMomentId &&
              moment.tripId == snapshot.plan.tripId &&
              moment.status == TripMomentStatus.active,
        )
        .toList(growable: false);
    if (matches.length != 1) {
      throw ArgumentError('active TripMoment is not in the current snapshot');
    }
    return matches.single;
  }

  String _nextIdempotencyKey() {
    final key = idempotencyKeyFactory().trim();
    if (key.isEmpty) {
      throw StateError('TripMoment idempotency key must not be blank');
    }
    return key;
  }
}

bool _containsTarget(TripTimelineView timeline, TripMomentTarget target) {
  final normalizedItemId = target.itemId.trim();
  if (target.dayIndex < 0 || normalizedItemId.isEmpty) {
    return false;
  }
  return timeline.days.any(
    (day) =>
        day.dayIndex == target.dayIndex &&
        day.items.any((item) => item.itemId == normalizedItemId),
  );
}
