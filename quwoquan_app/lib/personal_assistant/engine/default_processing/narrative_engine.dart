import 'package:quwoquan_app/personal_assistant/engine/default_processing/problem_framer.dart';

class NarrativeEngine {
  const NarrativeEngine();

  String heuristicReasoning({
    required ProblemFrame frame,
    required bool hasReferences,
  }) {
    if (frame.queryIntent == 'travelAlternativeOptions') {
      return hasReferences
          ? '已经把九寨沟方向的线索拆成路线、适用条件和取舍来整理，这样更容易直接比较。'
          : '先把九寨沟方向的判断维度立住，再继续补能真正影响选择的那一块。';
    }
    if (frame.queryIntent == 'wildlifeBestTime') {
      return hasReferences
          ? '已经把观赏时间拆成季节、时段和天气条件来整理，后面直接给可执行建议。'
          : '先把观赏时间最关键的三个判断维度立住，避免只给模糊说法。';
    }
    if (frame.problemClass == 'complex_reasoning') {
      return hasReferences
          ? '已经把拿到的资料按位置、价格和体验拆开整理，避免把不同维度揉在一起。'
          : '先把这类问题的关键维度搭起来，后续再沿着最缺的一块继续补。';
    }
    if (frame.primaryDomainId == 'weather') {
      return hasReferences ? '已经用核到的天气资料整理出一版稳妥结论。' : '先把天气查询还差的关键信息讲清楚，避免直接猜。';
    }
    return hasReferences ? '已经把核到的一致信息整理出来了。' : '先给一个不会误导你的下一步。';
  }

  String fallbackReason({
    required ProblemFrame frame,
    required List<String> missingCriticalSlots,
    required bool hasEvidence,
    required bool evidenceSafe,
    required bool hasToolError,
  }) {
    if (missingCriticalSlots.isNotEmpty) {
      return '我先不硬答，想先把会直接影响结论的关键信息补齐。';
    }
    if (!evidenceSafe && hasEvidence) {
      return '目前已经有一部分可参考信息，但还没稳到可以直接当成最终结论。';
    }
    if (!evidenceSafe && hasToolError) {
      return '这轮外部来源不够稳定，所以先只保留已经站稳的部分。';
    }
    if (frame.problemClass == 'complex_reasoning') {
      return '这类问题更怕方向混在一起，所以需要先把判断框架摆清楚。';
    }
    return '我先给你一个最低可用、不会误导你的版本。';
  }

  String askUserPrompt({required String slotId, required ProblemFrame frame}) {
    switch (slotId) {
      case 'city':
      case 'destination':
        return frame.primaryDomainId == 'weather'
            ? '请告诉我要查询的城市，比如“深圳”。'
            : '先告诉我你想去的城市或目的地，我再继续收敛。';
      case 'budget':
        return '再告诉我你的大概预算，我就能把推荐范围压得更准。';
      case 'days':
        return '告诉我准备玩几天几晚，我可以直接按天数来安排。';
      case 'companionType':
        return '如果你愿意，再说一下是亲子、情侣、朋友还是独自出行，我会把建议调得更贴合。';
      default:
        return '我还差一个会影响结论的关键信息，你补一句我就继续。';
    }
  }

  List<String> planningFramework(ProblemFrame frame) {
    if (frame.problemClass != 'complex_reasoning') {
      return const <String>['先确认问题里最影响结论的条件', '再核对最关键的外部依据', '最后只保留当前最稳的结论'];
    }
    return <String>[
      '先把目的地、预算和行程天数定下来，避免后面建议发散。',
      '再把“位置/通勤”“价格/档位”“近期体验”三块分开核对。',
      '最后只保留真正会影响你决策的差异点，避免一堆重复信息。',
    ];
  }
}
