// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/assistant_presentation_stream_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('snapshot patch commit 按 revision 投影并允许相同事件重放', () {
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
        AssistantStreamEventType.presentationPatch,
        revision: 2,
        payload: <String, dynamic>{
          'baseRevision': 1,
          'revision': 2,
          'patches': <Map<String, dynamic>>[
            <String, dynamic>{
              'operation': 'replace',
              'nodeId': 'root',
              'node': <String, dynamic>{
                ...(_documentJson(revision: 1)['nodes'] as List).single
                    as Map<String, dynamic>,
                'body': '更新后的行程',
              },
            },
          ],
        },
      ),
    );
    projection.apply(
      _event(
        AssistantStreamEventType.presentationCommit,
        revision: 3,
        payload: <String, dynamic>{'baseRevision': 2, 'revision': 3},
      ),
    );

    expect(projection.committed, isTrue);
    expect(projection.revision, 3);
    expect(projection.document?.revision, 3);
    expect(projection.document?.nodes.single.body, '更新后的行程');
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
          AssistantStreamEventType.presentationPatch,
          revision: 3,
          payload: <String, dynamic>{
            'baseRevision': 2,
            'revision': 3,
            'patches': const <Object>[],
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
        payload: <String, dynamic>{'baseRevision': 1, 'revision': 2},
      ),
    );
    expect(
      () => projection.apply(
        _event(
          AssistantStreamEventType.presentationPatch,
          revision: 3,
          payload: <String, dynamic>{
            'baseRevision': 2,
            'revision': 3,
            'patches': const <Object>[],
          },
        ),
      ),
      throwsFormatException,
    );
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
    'committedAt': '2026-07-31T12:00:00.000Z',
  };
}
