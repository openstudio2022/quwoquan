/// L1 Unit：交集 actionKey 端侧闭集常量与 metadata 闭集对齐 + 助手类分发判断。
///
/// 守护 N9：实体页等展示面按结构化 actionKey 分发，旧 `ask_xiaoqu` 死分支魔法字符串
/// 不再被识别为任何动作（强制走 metadata 闭集 actionKey）。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/core/constants/discovery_feed_text_constants.dart';

void main() {
  group('IntersectionActionKeys', () {
    test('常量值与 metadata 闭集（intersection_action_hint.yaml）逐一对齐', () {
      expect(IntersectionActionKeys.followPerson, 'follow_person');
      expect(IntersectionActionKeys.greetPerson, 'greet_person');
      expect(IntersectionActionKeys.messagePerson, 'message_person');
      expect(IntersectionActionKeys.viewSharedPeople, 'view_shared_people');
      expect(IntersectionActionKeys.joinCircle, 'join_circle');
      expect(IntersectionActionKeys.openDiscussion, 'open_discussion');
      expect(IntersectionActionKeys.openContent, 'open_content');
      expect(IntersectionActionKeys.openObject, 'open_object');
      expect(IntersectionActionKeys.followObject, 'follow_object');
      expect(IntersectionActionKeys.openRoute, 'open_route');
      expect(IntersectionActionKeys.createFollowup, 'create_followup');
      expect(IntersectionActionKeys.askAssistant, 'ask_assistant');
    });

    test('isAssistant：仅助手类（ask_assistant / create_followup）才打开小艺', () {
      expect(IntersectionActionKeys.isAssistant('ask_assistant'), isTrue);
      expect(IntersectionActionKeys.isAssistant('create_followup'), isTrue);
      // trim 容错（云侧可能带空白）。
      expect(IntersectionActionKeys.isAssistant(' ask_assistant '), isTrue);
      expect(IntersectionActionKeys.isAssistant('join_circle'), isFalse);
      expect(IntersectionActionKeys.isAssistant('greet_person'), isFalse);
      expect(IntersectionActionKeys.isAssistant('open_route'), isFalse);
      expect(IntersectionActionKeys.isAssistant(''), isFalse);
      // 旧死分支魔法字符串不再被视为助手动作。
      expect(IntersectionActionKeys.isAssistant('ask_xiaoqu'), isFalse);
    });
  });

  group('交集行动按钮文案 UI-SSOT 与 codegen 闭集对齐（§23 去桥接）', () {
    test('DiscoveryFeedText.intersectionActionLabels 键集 == codegen actionKey 闭集', () {
      // 每个注册表 actionKey 必须有 UI 文案，且不得有 codegen 闭集之外的孤儿文案。
      expect(
        DiscoveryFeedText.intersectionActionLabels.keys.toSet(),
        intersectionActionKeys.toSet(),
      );
    });

    test('每个 actionKey 文案非空', () {
      for (final key in intersectionActionKeys) {
        expect(
          DiscoveryFeedText.intersectionActionLabel(key).trim(),
          isNotEmpty,
          reason: key,
        );
      }
    });

    test('未知 actionKey 回退助手解释文案', () {
      expect(
        DiscoveryFeedText.intersectionActionLabel('unknown_future_action'),
        DiscoveryFeedText.intersectionActionLabels['ask_assistant'],
      );
    });
  });
}
