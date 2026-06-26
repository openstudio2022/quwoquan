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
      // §交集行动深化：同趣 / 同行 / 线下 / 实时 / 意图 行动阶梯常量。
      expect(IntersectionActionKeys.joinTopicRoom, 'join_topic_room');
      expect(IntersectionActionKeys.startCompanion, 'start_companion');
      expect(IntersectionActionKeys.joinTrip, 'join_trip');
      expect(IntersectionActionKeys.joinMeetup, 'join_meetup');
      expect(IntersectionActionKeys.meetNearby, 'meet_nearby');
      expect(IntersectionActionKeys.startVoiceRoom, 'start_voice_room');
      expect(IntersectionActionKeys.expressInterest, 'express_interest');
    });

    test('端侧常量集合与 codegen actionKey 闭集完全一致（无孤儿、无缺失）', () {
      const endpointConstants = <String>{
        IntersectionActionKeys.followPerson,
        IntersectionActionKeys.greetPerson,
        IntersectionActionKeys.messagePerson,
        IntersectionActionKeys.viewSharedPeople,
        IntersectionActionKeys.joinCircle,
        IntersectionActionKeys.openDiscussion,
        IntersectionActionKeys.openContent,
        IntersectionActionKeys.openObject,
        IntersectionActionKeys.followObject,
        IntersectionActionKeys.openRoute,
        IntersectionActionKeys.createFollowup,
        IntersectionActionKeys.askAssistant,
        IntersectionActionKeys.joinTopicRoom,
        IntersectionActionKeys.startCompanion,
        IntersectionActionKeys.joinTrip,
        IntersectionActionKeys.joinMeetup,
        IntersectionActionKeys.meetNearby,
        IntersectionActionKeys.startVoiceRoom,
        IntersectionActionKeys.expressInterest,
      };
      expect(endpointConstants, intersectionActionKeys.toSet());
    });

    test('isHeavySocialAction：重社交行动（同行/线下/实时/心动）识别', () {
      expect(IntersectionActionKeys.isHeavySocialAction('start_companion'), isTrue);
      expect(IntersectionActionKeys.isHeavySocialAction('join_trip'), isTrue);
      expect(IntersectionActionKeys.isHeavySocialAction('join_topic_room'), isTrue);
      expect(IntersectionActionKeys.isHeavySocialAction('meet_nearby'), isTrue);
      expect(IntersectionActionKeys.isHeavySocialAction('start_voice_room'), isTrue);
      expect(IntersectionActionKeys.isHeavySocialAction('express_interest'), isTrue);
      // trim 容错。
      expect(IntersectionActionKeys.isHeavySocialAction(' join_meetup '), isTrue);
      // 轻连接 / 助手类不算重社交行动。
      expect(IntersectionActionKeys.isHeavySocialAction('follow_person'), isFalse);
      expect(IntersectionActionKeys.isHeavySocialAction('open_route'), isFalse);
      expect(IntersectionActionKeys.isHeavySocialAction('ask_assistant'), isFalse);
      expect(IntersectionActionKeys.isHeavySocialAction(''), isFalse);
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
