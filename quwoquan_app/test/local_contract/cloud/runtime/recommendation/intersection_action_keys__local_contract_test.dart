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
      expect(IntersectionActionKeys.viewOfficialDeals, 'view_official_deals');
      expect(IntersectionActionKeys.bookTicket, 'book_ticket');
      expect(IntersectionActionKeys.bookHotel, 'book_hotel');
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
        IntersectionActionKeys.viewOfficialDeals,
        IntersectionActionKeys.bookTicket,
        IntersectionActionKeys.bookHotel,
      };
      expect(endpointConstants, intersectionActionKeys.toSet());
    });

    test('isCompanionAction：仅同行/线下约伴类（dispatch==companion）驱动「有人同行」', () {
      // dispatch==companion：真正的同行 / 行程 / 线下局 / 实时附近。
      expect(
        IntersectionActionKeys.isCompanionAction('start_companion'),
        isTrue,
      );
      expect(IntersectionActionKeys.isCompanionAction('join_trip'), isTrue);
      expect(IntersectionActionKeys.isCompanionAction('join_meetup'), isTrue);
      expect(IntersectionActionKeys.isCompanionAction('meet_nearby'), isTrue);
      // trim 容错。
      expect(
        IntersectionActionKeys.isCompanionAction(' start_companion '),
        isTrue,
      );
      // M0.7 语义修正：话题房 / 语音房 / 心动（dispatch==connect）不再误标为同行。
      expect(
        IntersectionActionKeys.isCompanionAction('join_topic_room'),
        isFalse,
      );
      expect(
        IntersectionActionKeys.isCompanionAction('start_voice_room'),
        isFalse,
      );
      expect(
        IntersectionActionKeys.isCompanionAction('express_interest'),
        isFalse,
      );
      // 私信（dispatch==message）与轻连接 / 助手类均非同行。
      expect(
        IntersectionActionKeys.isCompanionAction('message_person'),
        isFalse,
      );
      expect(
        IntersectionActionKeys.isCompanionAction('follow_person'),
        isFalse,
      );
      expect(
        IntersectionActionKeys.isCompanionAction('ask_assistant'),
        isFalse,
      );
      expect(IntersectionActionKeys.isCompanionAction(''), isFalse);
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

    test('isCommerce：仅 commerce dispatch 动作进入商用转化闸', () {
      expect(IntersectionActionKeys.isCommerce('view_official_deals'), isTrue);
      expect(IntersectionActionKeys.isCommerce('book_ticket'), isTrue);
      expect(IntersectionActionKeys.isCommerce('book_hotel'), isTrue);
      expect(IntersectionActionKeys.isCommerce('start_companion'), isFalse);
      expect(IntersectionActionKeys.isCommerce('open_route'), isFalse);
      expect(IntersectionActionKeys.isCommerce(''), isFalse);
    });

    test('分类判定委托 codegen dispatch，端无第二真相源（M0.7）', () {
      // 端 isAssistant / isCompanionAction 必须与 codegen actionKeyMeta.dispatch 完全一致，
      // 证明端不再手写重社交/助手枚举（守 R06 / R24 单一真相源）。
      for (final key in intersectionActionKeys) {
        final meta = intersectionActionKeyMeta[key];
        expect(meta, isNotNull, reason: key);
        expect(
          IntersectionActionKeys.isAssistant(key),
          meta!.dispatch == 'assistant',
          reason: '$key dispatch=${meta.dispatch}',
        );
        expect(
          IntersectionActionKeys.isCompanionAction(key),
          meta.dispatch == 'companion',
          reason: '$key dispatch=${meta.dispatch}',
        );
        expect(
          IntersectionActionKeys.isCommerce(key),
          meta.dispatch == 'commerce',
          reason: '$key dispatch=${meta.dispatch}',
        );
      }
      // dispatch 取值必须落在 codegen 闭集内。
      for (final meta in intersectionActionKeyMeta.values) {
        expect(intersectionActionDispatchKeys, contains(meta.dispatch));
      }
    });
  });

  group('交集行动按钮文案 UI-SSOT 与 codegen 闭集对齐（§23 去桥接）', () {
    test(
      'DiscoveryFeedText.intersectionActionLabels 键集 == codegen actionKey 闭集',
      () {
        // 每个注册表 actionKey 必须有 UI 文案，且不得有 codegen 闭集之外的孤儿文案。
        expect(
          DiscoveryFeedText.intersectionActionLabels.keys.toSet(),
          intersectionActionKeys.toSet(),
        );
      },
    );

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
