/// AssistantEntryView 的 chip 意图解析领域规则。
///
/// wire 上的 `actionType` / `value` 只在领域层判读一次；这里锁定闭集内取值、
/// 未知取值的兜底，以及「未知目的地不得被当成某个具体页面」。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_entry_view/domain/assistant_entry_chip_intent.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AssistantEntryChip;

AssistantEntryChip _chip({
  required String actionType,
  required String value,
  String label = 'chip-label',
}) => AssistantEntryChip(
  chipId: 'chip-$actionType-$value',
  label: label,
  actionType: actionType,
  value: value,
);

void main() {
  test('已登记的 route 目的地解析为命名目的地', () {
    for (final destination in AssistantEntryChipDestination.values) {
      final intent = resolveAssistantEntryChipIntent(
        _chip(actionType: 'route', value: destination.name),
      );

      expect(intent.kind, AssistantEntryChipIntentKind.namedDestination);
      expect(intent.destination, destination.name);
      expect(intent.query, isNull);
    }
  });

  test('未登记的 route 目的地退回助理会话且不携带查询', () {
    final intent = resolveAssistantEntryChipIntent(
      _chip(actionType: 'route', value: 'not-a-registered-destination'),
    );

    expect(intent.kind, AssistantEntryChipIntentKind.assistantSession);
    expect(intent.destination, isNull);
    expect(intent.query, isNull);
  });

  test('setting 解析为设置，不携带目的地或查询', () {
    final intent = resolveAssistantEntryChipIntent(
      _chip(actionType: 'setting', value: 'anything'),
    );

    expect(intent.kind, AssistantEntryChipIntentKind.settings);
    expect(intent.destination, isNull);
    expect(intent.query, isNull);
  });

  test('command 与未知 actionType 都进入会话并带上 chip 文案', () {
    for (final actionType in <String>['command', 'unknown-action-type']) {
      final intent = resolveAssistantEntryChipIntent(
        _chip(actionType: actionType, value: 'ignored', label: '帮我找搭子'),
      );

      expect(intent.kind, AssistantEntryChipIntentKind.assistantSession);
      expect(intent.query, '帮我找搭子');
      expect(intent.destination, isNull);
    }
  });
}
