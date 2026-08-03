import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/core/providers/app_providers.dart';

import 'assistant_facets_mock.dart';

export 'assistant_facets_mock.dart';

/// 把同一个替身实例绑定到全部 assistant Facet provider。
/// 对应旧 `assistantRepositoryProvider.overrideWithValue(...)` 的等价语义。
///
/// 这是测试容器 wiring，不是业务 Repository 聚合或 App 运行时 Provider。
List<Override> alphaAssistantFacetOverrides(AlphaAssistantFacets facets) {
  return <Override>[
    assistantSessionRunFacetProvider.overrideWithValue(facets),
    assistantRunControlFacetProvider.overrideWithValue(facets),
    assistantSkillCatalogFacetProvider.overrideWithValue(facets),
    assistantSkillSubscriptionFacetProvider.overrideWithValue(facets),
    assistantSkillUserSettingFacetProvider.overrideWithValue(facets),
    assistantSkillConsentFacetProvider.overrideWithValue(facets),
    assistantLearningFactAppendFacetProvider.overrideWithValue(facets),
    assistantPersonalizationFacetProvider.overrideWithValue(facets),
    assistantPersonalDataFacetProvider.overrideWithValue(facets),
    assistantPreferenceFactFacetProvider.overrideWithValue(facets),
    assistantSearchRunFacetProvider.overrideWithValue(facets),
    assistantCreationRunFacetProvider.overrideWithValue(facets),
  ];
}
