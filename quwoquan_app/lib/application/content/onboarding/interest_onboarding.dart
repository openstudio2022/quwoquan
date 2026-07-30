import 'package:uuid/uuid.dart';

/// 首启兴趣选择的持久化阶段；submitted 仅代表服务端确认成功。
enum InterestOnboardingStatus { unseen, skipped, pending, submitted }

final class InterestOnboardingDraft {
  const InterestOnboardingDraft({
    required this.taxonomyReleaseId,
    required this.clientEventId,
    required this.tagRefs,
    required this.status,
  });

  final String taxonomyReleaseId;
  final String clientEventId;
  final List<String> tagRefs;
  final InterestOnboardingStatus status;

  bool get hasSelection => tagRefs.isNotEmpty;

  InterestOnboardingDraft copyWith({
    String? taxonomyReleaseId,
    String? clientEventId,
    List<String>? tagRefs,
    InterestOnboardingStatus? status,
  }) => InterestOnboardingDraft(
    taxonomyReleaseId: taxonomyReleaseId ?? this.taxonomyReleaseId,
    clientEventId: clientEventId ?? this.clientEventId,
    tagRefs: tagRefs ?? this.tagRefs,
    status: status ?? this.status,
  );

  Map<String, Object?> toJson() => <String, Object?>{
    'taxonomyReleaseId': taxonomyReleaseId,
    'clientEventId': clientEventId,
    'tagRefs': tagRefs,
    'status': status.name,
  };

  static InterestOnboardingDraft? tryParse(Object? raw) {
    if (raw is! Map) return null;
    const canonicalKeys = <String>{
      'taxonomyReleaseId',
      'clientEventId',
      'tagRefs',
      'status',
    };
    // 本地草稿严格只认当前单轨形状；携带旧 catalogVersion
    // 或任何未知字段的存量输入直接 fail-closed，不双读或升级。
    if (raw.keys.any((key) => key is! String || !canonicalKeys.contains(key))) {
      return null;
    }
    final rawTaxonomyReleaseId = raw['taxonomyReleaseId'];
    final rawEventID = raw['clientEventId'];
    final rawStatus = raw['status'];
    final rawTags = raw['tagRefs'];
    if (rawTaxonomyReleaseId is! String ||
        rawEventID is! String ||
        rawStatus is! String ||
        rawTags is! List ||
        rawTags.any((tagRef) => tagRef is! String)) {
      return null;
    }
    final taxonomyReleaseId = rawTaxonomyReleaseId.trim();
    final eventID = rawEventID.trim();
    final status = InterestOnboardingStatus.values.where(
      (candidate) => candidate.name == rawStatus.trim(),
    );
    if (taxonomyReleaseId.isEmpty || eventID.isEmpty || status.isEmpty) {
      return null;
    }
    final tags = rawTags
        .cast<String>()
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .toSet()
        .toList(growable: false);
    return InterestOnboardingDraft(
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
    required String taxonomyReleaseId,
    required Iterable<String> tagRefs,
    InterestOnboardingDraft? previous,
  }) async {
    final canonicalReleaseID = _requiredTaxonomyReleaseID(taxonomyReleaseId);
    final tags = tagRefs
        .map((tagRef) => tagRef.trim())
        .where((tagRef) => tagRef.isNotEmpty)
        .toSet()
        .toList(growable: false);
    final reuseID =
        previous?.taxonomyReleaseId == canonicalReleaseID &&
        previous?.clientEventId.trim().isNotEmpty == true;
    final draft = InterestOnboardingDraft(
      taxonomyReleaseId: canonicalReleaseID,
      clientEventId: reuseID ? previous!.clientEventId : _newClientEventId(),
      tagRefs: tags,
      status: InterestOnboardingStatus.unseen,
    );
    await _draftStore.write(draft);
    return draft;
  }

  Future<InterestOnboardingDraft> skip({
    required String taxonomyReleaseId,
    InterestOnboardingDraft? previous,
  }) async {
    final canonicalReleaseID = _requiredTaxonomyReleaseID(taxonomyReleaseId);
    final draft = InterestOnboardingDraft(
      taxonomyReleaseId: canonicalReleaseID,
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

  static String _requiredTaxonomyReleaseID(String value) {
    final canonical = value.trim();
    if (canonical.isEmpty) {
      throw ArgumentError.value(value, 'taxonomyReleaseId', 'is required');
    }
    return canonical;
  }
}
