import 'package:quwoquan_app/assistant/assistant/assistant_run/domain/runtime_enums.dart';
import 'package:quwoquan_app/assistant/generated/contracts/skill_run.g.dart';

export 'package:quwoquan_app/assistant/generated/contracts/skill_run.g.dart';

extension SkillRunProblemClassX on SkillRun {
  ProblemClass get problemClassType => parseProblemClass(problemClass);
}
