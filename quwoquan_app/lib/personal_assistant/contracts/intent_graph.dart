export 'package:quwoquan_app/assistant/generated/contracts/intent_graph.g.dart';

import 'package:quwoquan_app/personal_assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/intent_graph.g.dart';

extension IntentGraphCompat on IntentGraph {
  bool get isMultiSkill =>
      problemShape == ProblemShape.multiSkill || secondarySkills.isNotEmpty;

  bool get isFastConvergence => problemClass.isFastConvergence;

  ProblemClass get problemClassType => problemClass;

  FreshnessNeed get freshnessNeedType => freshnessNeed;

  AnswerShape get answerShapeType => answerShape;

  String get problemShapeWireName => problemShape.wireName;

  String get problemClassWireName => problemClass.wireName;

  String get freshnessNeedWireName => freshnessNeed.wireName;

  String get answerShapeWireName => answerShape.wireName;
}
