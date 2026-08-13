// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/assistant_presentation_stream_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('snapshot commit 按 revision 投影并允许相同事件重放', () {
    final projection = AssistantPresentationStreamProjection();
    final snapshot = _event(
      AssistantStreamEventType.presentationSnapshot,
      revision: 1,
      payload: <String, dynamic>{
        'baseRevision': 0,
        'revision': 1,
        'document': _documentJson(revision: 1),
      },
    );
    projection.apply(snapshot);
    projection.apply(snapshot);
    expect(projection.document?.nodes.single.body, '原始行程');

    projection.apply(
      _event(
        AssistantStreamEventType.presentationCommit,
        revision: 2,
        payload: <String, dynamic>{
          'baseRevision': 1,
          'revision': 2,
          'committedAt': '2026-07-31T12:00:03.000Z',
        },
      ),
    );

    expect(projection.committed, isTrue);
    expect(projection.revision, 2);
    expect(projection.document?.revision, 2);
    expect(projection.document?.committedAt, '2026-07-31T12:00:03.000Z');
    expect(projection.document?.nodes.single.body, '原始行程');
  });

  test('gap、冲突重放与 commit 后写入全部 fail closed', () {
    final projection = AssistantPresentationStreamProjection();
    projection.apply(
      _event(
        AssistantStreamEventType.presentationSnapshot,
        revision: 1,
        payload: <String, dynamic>{
          'baseRevision': 0,
          'revision': 1,
          'document': _documentJson(revision: 1),
        },
      ),
    );

    expect(
      () => projection.apply(
        _event(
          AssistantStreamEventType.presentationCommit,
          revision: 3,
          payload: <String, dynamic>{
            'baseRevision': 2,
            'revision': 3,
            'committedAt': '2026-07-31T12:00:03.000Z',
          },
        ),
      ),
      throwsFormatException,
    );
    expect(
      () => projection.apply(
        _event(
          AssistantStreamEventType.presentationSnapshot,
          revision: 1,
          payload: <String, dynamic>{
            'baseRevision': 0,
            'revision': 1,
            'document': _documentJson(revision: 1, body: '冲突内容'),
          },
        ),
      ),
      throwsFormatException,
    );

    projection.apply(
      _event(
        AssistantStreamEventType.presentationCommit,
        revision: 2,
        payload: <String, dynamic>{
          'baseRevision': 1,
          'revision': 2,
          'committedAt': '2026-07-31T12:00:02.000Z',
        },
      ),
    );
    expect(
      () => projection.apply(
        _event(
          AssistantStreamEventType.presentationCommit,
          revision: 3,
          payload: <String, dynamic>{
            'baseRevision': 2,
            'revision': 3,
            'committedAt': '2026-07-31T12:00:03.000Z',
          },
        ),
      ),
      throwsFormatException,
    );
  });

  test('commit 缺失或伪造时间时不改变尚未提交的投影', () {
    for (final committedAt in <Object?>[
      null,
      '',
      20260731,
      '2026-07-31',
      'not-a-timestamp',
    ]) {
      final projection = AssistantPresentationStreamProjection();
      projection.apply(
        _event(
          AssistantStreamEventType.presentationSnapshot,
          revision: 1,
          payload: <String, dynamic>{
            'baseRevision': 0,
            'revision': 1,
            'document': _documentJson(revision: 1),
          },
        ),
      );
      final payload = <String, dynamic>{'baseRevision': 1, 'revision': 2};
      if (committedAt != null) {
        payload['committedAt'] = committedAt;
      }

      expect(
        () => projection.apply(
          _event(
            AssistantStreamEventType.presentationCommit,
            revision: 2,
            payload: payload,
          ),
        ),
        throwsFormatException,
      );
      expect(projection.committed, isFalse);
      expect(projection.revision, 1);
      expect(projection.document?.committedAt, isEmpty);
    }
  });

  test('未提交 snapshot 可在恢复后继续 commit，伪造 seed 时间 fail closed', () {
    final projection = AssistantPresentationStreamProjection();
    projection.seed(
      AssistantPresentationDocumentWire.fromJson(_documentJson(revision: 1)),
    );

    expect(projection.revision, 1);
    expect(projection.committed, isFalse);
    projection.apply(
      _event(
        AssistantStreamEventType.presentationCommit,
        revision: 2,
        payload: <String, dynamic>{
          'baseRevision': 1,
          'revision': 2,
          'committedAt': '2026-07-31T12:00:02Z',
        },
      ),
    );
    expect(projection.committed, isTrue);
    expect(projection.document?.committedAt, '2026-07-31T12:00:02Z');

    final invalid = AssistantPresentationStreamProjection();
    expect(
      () => invalid.seed(
        AssistantPresentationDocumentWire.fromJson(
          _documentJson(revision: 1, committedAt: 'not-a-timestamp'),
        ),
      ),
      throwsFormatException,
    );
    expect(invalid.document, isNull);
    expect(invalid.revision, 0);
  });

  test('小数 presentation revision 不得截断后进入投影', () {
    for (final payload in <Map<String, dynamic>>[
      <String, dynamic>{
        'baseRevision': 0.5,
        'revision': 1,
        'document': _documentJson(revision: 1),
      },
      <String, dynamic>{
        'baseRevision': 0,
        'revision': 1.5,
        'document': _documentJson(revision: 1),
      },
    ]) {
      final projection = AssistantPresentationStreamProjection();
      expect(
        () => projection.apply(
          _event(
            AssistantStreamEventType.presentationSnapshot,
            revision: 1,
            payload: payload,
          ),
        ),
        throwsFormatException,
      );
      expect(projection.document, isNull);
      expect(projection.revision, 0);
    }
  });

  test('snapshot 不得伪造已提交时间', () {
    final projection = AssistantPresentationStreamProjection();
    expect(
      () => projection.apply(
        _event(
          AssistantStreamEventType.presentationSnapshot,
          revision: 1,
          payload: <String, dynamic>{
            'baseRevision': 0,
            'revision': 1,
            'document': _documentJson(
              revision: 1,
              committedAt: '2026-07-31T12:00:00Z',
            ),
          },
        ),
      ),
      throwsFormatException,
    );
    expect(projection.document, isNull);
    expect(projection.revision, 0);
  });
}

AssistantStreamEventWire _event(
  AssistantStreamEventType type, {
  required int revision,
  required Map<String, dynamic> payload,
}) {
  return AssistantStreamEventWire(
    schema: 'assistant_stream_event',
    eventId: 'event_$revision',
    sessionId: 'session_presentation',
    runId: 'arn_presentation',
    seq: revision,
    eventType: type,
    payload: payload,
    createdAt: '2026-07-31T12:00:00.000Z',
  );
}

Map<String, dynamic> _documentJson({
  required int revision,
  String body = '原始行程',
  String committedAt = '',
}) {
  const digest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  return <String, dynamic>{
    'templateRef': 'travel.timeline@$digest',
    'templateDigest': digest,
    'revision': revision,
    'rootNodeId': 'root',
    'nodes': <Map<String, dynamic>>[
      <String, dynamic>{
        'nodeId': 'root',
        'parentNodeId': '',
        'order': 0,
        'kind': 'timeline',
        'title': '旅行时间线',
        'body': body,
        'data': const <String, dynamic>{},
        'binding': const <String, dynamic>{},
        'style': const <String, dynamic>{},
        'accessibility': const <String, dynamic>{'semanticLabel': '旅行时间线'},
      },
    ],
    'dataDigest':
        'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'selectedVariant': 'compact',
    'fallbackMarkdown': '## 旅行行程\n完整降级内容',
    'fallbackPlainText': '旅行行程 完整降级内容',
    'committedAt': committedAt,
  };
}
