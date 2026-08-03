import 'package:quwoquan_app/application/travel/trip_plan_creation_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 创建 Trip 时冻结的用户意图。网络重试必须复用同一实例，
/// 从而保持命令载荷和 idempotency key 字节级稳定。
final class TripPlanCreationIntent {
  const TripPlanCreationIntent._({
    required this.idempotencyKey,
    this.directCommand,
    this.templateCommand,
  });

  final String idempotencyKey;
  final CreateTripPlanCommand? directCommand;
  final CreateTripPlanFromTemplateCommand? templateCommand;
}

final class TripPlanCreationCoordinator {
  TripPlanCreationCoordinator(this._facet, this._idempotencyKeyFactory);

  final TripPlanCreationFacet _facet;
  final String Function() _idempotencyKeyFactory;

  TripPlanCreationIntent prepareDraft({
    required String title,
    DateTime? startAt,
    DateTime? endAt,
  }) {
    final normalizedTitle = title.trim();
    if (normalizedTitle.isEmpty) {
      throw ArgumentError.value(title, 'title', 'must not be blank');
    }
    _validateRange(startAt, endAt);
    return TripPlanCreationIntent._(
      idempotencyKey: _nextKey(),
      directCommand: CreateTripPlanCommand(
        title: normalizedTitle,
        startAt: startAt?.toUtc(),
        endAt: endAt?.toUtc(),
        items: const <TripPlanItemInput>[],
      ),
    );
  }

  TripPlanCreationIntent prepareFromTemplate({
    required String templateId,
    String? title,
    DateTime? startAt,
    DateTime? endAt,
  }) {
    final normalizedTemplateId = templateId.trim();
    final normalizedTitle = title?.trim();
    if (normalizedTemplateId.isEmpty) {
      throw ArgumentError.value(templateId, 'templateId', 'must not be blank');
    }
    _validateRange(startAt, endAt);
    return TripPlanCreationIntent._(
      idempotencyKey: _nextKey(),
      templateCommand: CreateTripPlanFromTemplateCommand(
        templateId: normalizedTemplateId,
        title: normalizedTitle == null || normalizedTitle.isEmpty
            ? null
            : normalizedTitle,
        startAt: startAt?.toUtc(),
        endAt: endAt?.toUtc(),
      ),
    );
  }

  Future<TripPlanCommandResult> create(TripPlanCreationIntent intent) {
    final direct = intent.directCommand;
    if (direct != null) {
      return _facet.create(direct, idempotencyKey: intent.idempotencyKey);
    }
    final template = intent.templateCommand;
    if (template != null) {
      return _facet.createFromTemplate(
        template,
        idempotencyKey: intent.idempotencyKey,
      );
    }
    throw StateError('TripPlanCreationIntent has no command');
  }

  String _nextKey() {
    final value = _idempotencyKeyFactory().trim();
    if (value.isEmpty) {
      throw StateError('idempotencyKeyFactory returned a blank key');
    }
    return value;
  }

  static void _validateRange(DateTime? startAt, DateTime? endAt) {
    if (startAt != null && endAt != null && endAt.isBefore(startAt)) {
      throw ArgumentError.value(endAt, 'endAt', 'must not precede startAt');
    }
  }
}
