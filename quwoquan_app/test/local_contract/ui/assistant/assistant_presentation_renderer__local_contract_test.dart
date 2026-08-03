// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_presentation_document.g.dart';
import 'package:quwoquan_app/assistant/generated/contracts/assistant_presentation_node.g.dart';
import 'package:quwoquan_app/ui/assistant/widgets/presentation/assistant_presentation_renderer.dart';

void main() {
  testWidgets('同一旅行文档在窄宽屏与大字体下保留事实和语义', (tester) async {
    final document = _travelDocument();
    for (final size in <Size>[const Size(320, 800), const Size(1024, 800)]) {
      await tester.binding.setSurfaceSize(size);
      await tester.pumpWidget(
        _host(document, textScaler: const TextScaler.linear(1.6)),
      );
      await tester.pumpAndSettle();

      expect(find.text('川西三日行程'), findsOneWidget);
      expect(find.text('第一天：成都出发'), findsOneWidget);
      expect(find.bySemanticsLabel('旅行行程时间线'), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
    await tester.binding.setSurfaceSize(null);
  });

  testWidgets('未知节点确定性显示非空 Markdown fallback 并观测原因', (tester) async {
    final reasons = <String>[];
    final invalid = _travelDocument(
      nodes: <AssistantPresentationNodeWire>[
        const AssistantPresentationNodeWire(
          nodeId: 'root',
          kind: AssistantPresentationNodeKind.unknown,
          body: '不能执行的未知节点',
        ),
      ],
    );
    await tester.pumpWidget(
      _host(invalid, onFallback: (reason, _) => reasons.add(reason)),
    );
    await tester.pump();

    expect(find.text('## 完整旅行答案\n请按原始行程出发。'), findsOneWidget);
    expect(find.text('不能执行的未知节点'), findsNothing);
    expect(reasons, <String>['unsupported_node']);
    expect(tester.takeException(), isNull);
  });

  testWidgets('typed action 仅通过显式 handler 执行且危险 payload 降级', (tester) async {
    final actions = <AssistantActionIntentWire>[];
    final valid = _travelDocument(
      nodes: <AssistantPresentationNodeWire>[
        AssistantPresentationNodeWire(
          nodeId: 'root',
          kind: AssistantPresentationNodeKind.confirmationCard,
          title: '确认继续',
          body: '继续检查天气',
          action: const AssistantActionIntentWire(
            intentId: 'continue_weather',
            operation: 'ContinueAssistantToolUse',
            objectTypeRef: 'assistant_tool_use',
            objectId: 'tool_weather',
            payload: <String, dynamic>{'approved': true},
            requiresConfirmation: true,
          ),
          accessibility: const AssistantPresentationAccessibilityWire(
            semanticLabel: '确认天气工具',
          ),
        ),
      ],
    );
    await tester.pumpWidget(_host(valid, onAction: actions.add));
    await tester.tap(find.byType(CupertinoButton).last);
    await tester.pump();
    expect(actions.single.operation, 'ContinueAssistantToolUse');

    final unsafe = _travelDocument(
      nodes: <AssistantPresentationNodeWire>[
        const AssistantPresentationNodeWire(
          nodeId: 'root',
          kind: AssistantPresentationNodeKind.confirmationCard,
          title: '未知跳转',
          action: AssistantActionIntentWire(
            intentId: 'unsafe',
            operation: 'ContinueAssistantToolUse',
            payload: <String, dynamic>{'route': '/admin'},
          ),
        ),
      ],
    );
    await tester.pumpWidget(_host(unsafe, onAction: actions.add));
    await tester.pump();
    expect(find.text('## 完整旅行答案\n请按原始行程出发。'), findsOneWidget);
    expect(find.text('未知跳转'), findsNothing);
    expect(actions, hasLength(1));
  });

  testWidgets('route_map 仅渲染 canonical 地点引用、路线和随拍标记', (tester) async {
    final document = _travelDocument(
      nodes: <AssistantPresentationNodeWire>[
        AssistantPresentationNodeWire(
          nodeId: 'root',
          kind: AssistantPresentationNodeKind.routeMap,
          title: '第二天路线',
          data: _routeMapData(),
          accessibility: const AssistantPresentationAccessibilityWire(
            semanticLabel: '第二天旅行路线图',
          ),
        ),
      ],
    );
    await tester.pumpWidget(_host(document));
    await tester.pump();

    expect(find.text('第二天路线'), findsOneWidget);
    expect(find.text('灵隐寺'), findsOneWidget);
    expect(find.text('西湖'), findsOneWidget);
    expect(find.text('1'), findsNWidgets(2));
    expect(find.bySemanticsLabel('第二天旅行路线图'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('route_map 拒绝任意 URL 或 Provider 参数并确定性降级', (tester) async {
    final unsafeData = _routeMapData()..['providerUrl'] = 'https://maps.test';
    final document = _travelDocument(
      nodes: <AssistantPresentationNodeWire>[
        AssistantPresentationNodeWire(
          nodeId: 'root',
          kind: AssistantPresentationNodeKind.routeMap,
          title: '不安全路线',
          data: unsafeData,
        ),
      ],
    );
    final reasons = <String>[];
    await tester.pumpWidget(
      _host(document, onFallback: (reason, _) => reasons.add(reason)),
    );
    await tester.pump();

    expect(find.text('## 完整旅行答案\n请按原始行程出发。'), findsOneWidget);
    expect(find.text('不安全路线'), findsNothing);
    expect(reasons, <String>['invalid_route_map']);
  });
}

Map<String, dynamic> _routeMapData() => <String, dynamic>{
  'tripId': 'trip_hangzhou',
  'revisionId': 'revision_2',
  'sourceDigest':
      'sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
  'stops': <Map<String, dynamic>>[
    <String, dynamic>{
      'placeRef': <String, dynamic>{
        'objectTypeRef': 'entity.Place',
        'objectId': 'lingyin_temple',
      },
      'dayIndex': 2,
      'order': 0,
      'itemId': 'item_lingyin',
      'title': '灵隐寺',
    },
    <String, dynamic>{
      'placeRef': <String, dynamic>{
        'objectTypeRef': 'entity.Place',
        'objectId': 'west_lake',
      },
      'dayIndex': 2,
      'order': 1,
      'itemId': 'item_west_lake',
      'title': '西湖',
    },
  ],
  'segments': <Map<String, dynamic>>[
    <String, dynamic>{
      'fromPlaceRef': <String, dynamic>{
        'objectTypeRef': 'entity.Place',
        'objectId': 'lingyin_temple',
      },
      'toPlaceRef': <String, dynamic>{
        'objectTypeRef': 'entity.Place',
        'objectId': 'west_lake',
      },
      'modeToken': 'transit',
      'order': 0,
    },
  ],
  'markers': <Map<String, dynamic>>[
    <String, dynamic>{
      'momentId': 'moment_lingyin',
      'placeRef': <String, dynamic>{
        'objectTypeRef': 'entity.Place',
        'objectId': 'lingyin_temple',
      },
      'dayIndex': 2,
      'itemId': 'item_lingyin',
    },
  ],
};

Widget _host(
  AssistantPresentationDocumentWire document, {
  TextScaler textScaler = TextScaler.noScaling,
  AssistantPresentationActionHandler? onAction,
  AssistantPresentationFallbackObserver? onFallback,
}) {
  return MaterialApp(
    home: MediaQuery(
      data: MediaQueryData(
        size: const Size(390, 800),
        textScaler: textScaler,
        disableAnimations: true,
      ),
      child: Scaffold(
        body: AssistantPresentationRenderer(
          document: document,
          textColor: Colors.black,
          markdownBuilder: Text.new,
          onAction: onAction,
          onFallback: onFallback,
        ),
      ),
    ),
  );
}

AssistantPresentationDocumentWire _travelDocument({
  List<AssistantPresentationNodeWire>? nodes,
}) {
  const templateDigest =
      'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
  return AssistantPresentationDocumentWire(
    templateRef: 'travel.timeline@$templateDigest',
    templateDigest: templateDigest,
    revision: 2,
    rootNodeId: 'root',
    nodes:
        nodes ??
        const <AssistantPresentationNodeWire>[
          AssistantPresentationNodeWire(
            nodeId: 'root',
            kind: AssistantPresentationNodeKind.timeline,
            title: '川西三日行程',
            accessibility: AssistantPresentationAccessibilityWire(
              semanticLabel: '旅行行程时间线',
            ),
          ),
          AssistantPresentationNodeWire(
            nodeId: 'day_one',
            parentNodeId: 'root',
            kind: AssistantPresentationNodeKind.text,
            body: '第一天：成都出发',
          ),
        ],
    dataDigest:
        'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    selectedVariant: 'compact',
    fallbackMarkdown: '## 完整旅行答案\n请按原始行程出发。',
    fallbackPlainText: '完整旅行答案，请按原始行程出发。',
    committedAt: '2026-07-31T12:00:00.000Z',
  );
}
