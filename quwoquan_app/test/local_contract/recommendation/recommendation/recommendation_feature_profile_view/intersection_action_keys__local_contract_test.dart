/// L1 Unit：交集 actionKey 端侧闭集常量与 metadata 闭集对齐 + 助手类分发判断。
///
/// 守护 N9：实体页等展示面按结构化 actionKey 分发，旧 `ask_xiaoqu` 死分支魔法字符串
/// 不再被识别为任何动作（强制走 metadata 闭集 actionKey）。
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';

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
      expect(IntersectionActionKeys.startGathering, 'start_gathering');
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
        IntersectionActionKeys.startGathering,
      };
      expect(endpointConstants, intersectionActionKeys.toSet());
    });

    test('isGatheringAction：仅同行/线下约伴类（dispatch==gathering）驱动「有人同行」', () {
      // dispatch==gathering：真正的同行 / 线下局 / 实时附近。
      expect(
        IntersectionActionKeys.isGatheringAction('start_gathering'),
        isTrue,
      );
      // trim 容错。
      expect(
        IntersectionActionKeys.isGatheringAction(' start_gathering '),
        isTrue,
      );
      // 私信（dispatch==message）与轻连接 / 助手类均非同行。
      expect(
        IntersectionActionKeys.isGatheringAction('message_person'),
        isFalse,
      );
      expect(
        IntersectionActionKeys.isGatheringAction('follow_person'),
        isFalse,
      );
      expect(
        IntersectionActionKeys.isGatheringAction('ask_assistant'),
        isFalse,
      );
      expect(IntersectionActionKeys.isGatheringAction(''), isFalse);
      // 已退役 actionKey（registry.actionKeyMigrations）不得被端侧继续识别，
      // 否则云侧改名后端侧仍会渲染出无承接页的入口。
      for (final retired in <String>[
        'start_companion',
        'join_trip',
        'join_meetup',
        'start_voice_room',
      ]) {
        expect(IntersectionActionKeys.isGatheringAction(retired), isFalse);
        expect(intersectionActionKeys, isNot(contains(retired)));
      }
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

    test('分类判定委托 codegen dispatch，端无第二真相源（M0.7）', () {
      // 端 isAssistant / isGatheringAction 必须与 codegen actionKeyMeta.dispatch 完全一致，
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
          IntersectionActionKeys.isGatheringAction(key),
          meta.dispatch == 'gathering',
          reason: '$key dispatch=${meta.dispatch}',
        );
      }
      // dispatch 取值必须落在 codegen 闭集内。
      for (final meta in intersectionActionKeyMeta.values) {
        expect(intersectionActionDispatchKeys, contains(meta.dispatch));
      }
    });
  });
}
