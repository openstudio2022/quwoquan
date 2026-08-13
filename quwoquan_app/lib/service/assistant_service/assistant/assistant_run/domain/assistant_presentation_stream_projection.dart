import 'dart:convert';

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        AssistantPresentationDocumentWire,
        AssistantStreamEventType,
        AssistantStreamEventWire;

/// Reduces ordered presentation SSE items into one immutable document.
///
/// Replayed items are idempotent only when their complete payload matches.
/// Gaps, conflicts and post-commit writes fail closed so the renderer can
/// show the document's Markdown/plain-text fallback.
class AssistantPresentationStreamProjection {
  AssistantPresentationDocumentWire? _document;
  int _revision = 0;
  bool _committed = false;
  final Map<int, String> _eventPayloads = <int, String>{};

  AssistantPresentationDocumentWire? get document => _document;
  int get revision => _revision;
  bool get committed => _committed;

  void seed(AssistantPresentationDocumentWire document) {
    if (document.revision <= 0) {
      throw const FormatException('seed presentation revision is invalid');
    }
    final committedAt = document.committedAt;
    final committed = committedAt.isNotEmpty;
    if (committed && _committedAtFromPayload(committedAt) == null) {
      throw const FormatException(
        'seed presentation commit timestamp is invalid',
      );
    }
    _document = document;
    _revision = document.revision;
    _committed = committed;
    _eventPayloads.clear();
  }

  void reset() {
    _document = null;
    _revision = 0;
    _committed = false;
    _eventPayloads.clear();
  }

  AssistantPresentationDocumentWire? apply(AssistantStreamEventWire event) {
    if (!_isPresentationEvent(event.eventType)) {
      return _document;
    }
    final payload = event.payload;
    final baseRevision = _wireInt(payload['baseRevision']);
    final revision = _wireInt(payload['revision']);
    if (revision <= 0) {
      throw const FormatException('presentation revision must be positive');
    }
    final encodedPayload = jsonEncode(<String, Object?>{
      'eventType': event.eventType.wireName,
      'payload': payload,
    });
    final replayed = _eventPayloads[revision];
    if (replayed != null) {
      if (replayed == encodedPayload) {
        return _document;
      }
      throw const FormatException('conflicting presentation event replay');
    }
    final replacesCommittedDocument =
        event.eventType == AssistantStreamEventType.presentationSnapshot &&
        _committed;
    if ((!replacesCommittedDocument && _committed) ||
        baseRevision != _revision ||
        revision != _revision + 1) {
      throw const FormatException('presentation revision is out of order');
    }

    switch (event.eventType) {
      case AssistantStreamEventType.presentationSnapshot:
        if ((!replacesCommittedDocument && _revision != 0) ||
            payload['document'] is! Map) {
          throw const FormatException('invalid presentation snapshot');
        }
        final parsed = AssistantPresentationDocumentWire.fromJson(
          (payload['document'] as Map).cast<String, dynamic>(),
        );
        if (parsed.revision != revision || parsed.committedAt.isNotEmpty) {
          throw const FormatException(
            'presentation snapshot revision or commit state is invalid',
          );
        }
        _document = parsed;
        _committed = false;
        break;
      case AssistantStreamEventType.presentationCommit:
        final current = _document;
        if (_revision == 0 || current == null) {
          throw const FormatException('invalid presentation commit');
        }
        final committedAt = _committedAtFromPayload(payload['committedAt']);
        if (committedAt == null) {
          throw const FormatException(
            'presentation commit timestamp is missing or invalid',
          );
        }
        _document = _copyDocument(
          current,
          revision: revision,
          committedAt: committedAt,
        );
        _committed = true;
        break;
      default:
        throw const FormatException('unsupported presentation event');
    }
    _revision = revision;
    _eventPayloads[revision] = encodedPayload;
    return _document;
  }

  String? _committedAtFromPayload(Object? rawValue) {
    if (rawValue is! String) {
      return null;
    }
    final value = rawValue.trim();
    if (!RegExp(
      r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})$',
    ).hasMatch(value)) {
      return null;
    }
    return DateTime.tryParse(value) == null ? null : value;
  }

}

bool _isPresentationEvent(AssistantStreamEventType type) => switch (type) {
  AssistantStreamEventType.presentationSnapshot ||
  AssistantStreamEventType.presentationCommit => true,
  _ => false,
};

AssistantPresentationDocumentWire _copyDocument(
  AssistantPresentationDocumentWire document, {
  required int revision,
  String? committedAt,
}) {
  return AssistantPresentationDocumentWire(
    templateRef: document.templateRef,
    templateDigest: document.templateDigest,
    revision: revision,
    rootNodeId: document.rootNodeId,
    nodes: document.nodes,
    dataDigest: document.dataDigest,
    selectedVariant: document.selectedVariant,
    fallbackMarkdown: document.fallbackMarkdown,
    fallbackPlainText: document.fallbackPlainText,
    committedAt: committedAt ?? document.committedAt,
  );
}

int _wireInt(Object? value) {
  if (value is! num || !value.isFinite || value != value.truncateToDouble()) {
    return -1;
  }
  return value.toInt();
}
