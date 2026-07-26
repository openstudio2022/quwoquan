import 'package:uuid/uuid.dart';

/// 首启兴趣选择的持久化阶段；submitted 仅代表服务端确认成功。
enum InterestOnboardingStatus { unseen, skipped, pending, submitted }

final class InterestOnboardingDraft {
  const InterestOnboardingDraft({
    required this.catalogVersion,
    required this.taxonomyReleaseId,
    required this.clientEventId,
    required this.tagRefs,
    required this.status,
  });

  final String catalogVersion;
  final String taxonomyReleaseId;
  final String clientEventId;
  final List<String> tagRefs;
  final InterestOnboardingStatus status;

  bool get hasSelection => tagRefs.isNotEmpty;

  InterestOnboardingDraft copyWith({
    String? catalogVersion,
    String? taxonomyReleaseId,
    String? clientEventId,
    List<String>? tagRefs,
    InterestOnboardingStatus? status,
  }) => InterestOnboardingDraft(
    catalogVersion: catalogVersion ?? this.catalogVersion,
    taxonomyReleaseId: taxonomyReleaseId ?? this.taxonomyReleaseId,
    clientEventId: clientEventId ?? this.clientEventId,
    tagRefs: tagRefs ?? this.tagRefs,
    status: status ?? this.status,
  );

  Map<String, Object?> toJson() => <String, Object?>{
    'catalogVersion': catalogVersion,
    'taxonomyReleaseId': taxonomyReleaseId,
    'clientEventId': clientEventId,
    'tagRefs': tagRefs,
    'status': status.name,
  };

  static InterestOnboardingDraft? tryParse(Object? raw) {
    if (raw is! Map) return null;
    final version = (raw['catalogVersion'] ?? '').toString().trim();
    final taxonomyReleaseId = (raw['taxonomyReleaseId'] ?? '')
        .toString()
        .trim();
    final eventID = (raw['clientEventId'] ?? '').toString().trim();
    final status = InterestOnboardingStatus.values.where(
      (candidate) => candidate.name == (raw['status'] ?? '').toString().trim(),
    );
    if (version.isEmpty ||
        taxonomyReleaseId.isEmpty ||
        eventID.isEmpty ||
        status.isEmpty) {
      return null;
    }
    final tags = (raw['tagRefs'] as List? ?? const <Object?>[])
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList(growable: false);
    return InterestOnboardingDraft(
      catalogVersion: version,
      taxonomyReleaseId: taxonomyReleaseId,
      clientEventId: eventID,
      tagRefs: tags,
      status: status.first,
    );
  }
}

abstract interface class InterestOnboardingDraftStore {
  Future<InterestOnboardingDraft?> read();
  Future<void> write(InterestOnboardingDraft draft);
}

/// 确认型端口：网络失败必须抛出，禁止转入尽力行为队列。
abstract interface class ConfirmedOnboardingInterestWriter {
  Future<void> submit({
    required String clientEventId,
    required String catalogVersion,
    required String taxonomyReleaseId,
    required List<String> tagRefs,
  });
}

final class InterestOnboardingCoordinator {
  const InterestOnboardingCoordinator({
    required this._draftStore,
    required this._writer,
  });

  static const Uuid _uuid = Uuid();

  final InterestOnboardingDraftStore _draftStore;
  final ConfirmedOnboardingInterestWriter _writer;

  Future<InterestOnboardingDraft?> load() => _draftStore.read();

  Future<InterestOnboardingDraft> select({
    required String catalogVersion,
    required String taxonomyReleaseId,
    required Iterable<String> tagRefs,
    InterestOnboardingDraft? previous,
  }) async {
    final tags = tagRefs
        .map((tagRef) => tagRef.trim())
        .where((tagRef) => tagRef.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final reuseID =
        previous?.catalogVersion == catalogVersion &&
        previous?.taxonomyReleaseId == taxonomyReleaseId &&
        previous?.clientEventId.trim().isNotEmpty == true;
    final draft = InterestOnboardingDraft(
      catalogVersion: catalogVersion,
      taxonomyReleaseId: taxonomyReleaseId,
      clientEventId: reuseID ? previous!.clientEventId : _newClientEventId(),
      tagRefs: tags,
      status: InterestOnboardingStatus.unseen,
    );
    await _draftStore.write(draft);
    return draft;
  }

  Future<InterestOnboardingDraft> skip({
    required String catalogVersion,
    required String taxonomyReleaseId,
    InterestOnboardingDraft? previous,
  }) async {
    final draft = InterestOnboardingDraft(
      catalogVersion: catalogVersion,
      taxonomyReleaseId: taxonomyReleaseId,
      clientEventId: previous?.clientEventId.trim().isNotEmpty == true
          ? previous!.clientEventId
          : _newClientEventId(),
      tagRefs: const <String>[],
      status: InterestOnboardingStatus.skipped,
    );
    await _draftStore.write(draft);
    return draft;
  }

  Future<InterestOnboardingDraft> submit(InterestOnboardingDraft draft) async {
    if (!draft.hasSelection) {
      throw ArgumentError.value(draft.tagRefs, 'tagRefs', 'requires a tag');
    }
    final pending = draft.copyWith(status: InterestOnboardingStatus.pending);
    await _draftStore.write(pending);
    try {
      await _writer.submit(
        clientEventId: pending.clientEventId,
        catalogVersion: pending.catalogVersion,
        taxonomyReleaseId: pending.taxonomyReleaseId,
        tagRefs: pending.tagRefs,
      );
    } catch (_) {
      await _draftStore.write(pending);
      rethrow;
    }
    final submitted = pending.copyWith(
      status: InterestOnboardingStatus.submitted,
    );
    await _draftStore.write(submitted);
    return submitted;
  }

  static String _newClientEventId() => 'onboarding:${_uuid.v4()}';
}
