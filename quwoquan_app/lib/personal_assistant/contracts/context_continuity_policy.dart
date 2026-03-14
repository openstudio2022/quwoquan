export 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/context_continuity_policy.g.dart';

import 'package:quwoquan_app/personal_assistant/runtime/generated/contracts/context_continuity_policy.g.dart';

extension ContextContinuityPolicyCompat on ContextContinuityPolicy {
  bool get allowRecentCityMentions => allowLocationHints && allowHistorySummary;
}
