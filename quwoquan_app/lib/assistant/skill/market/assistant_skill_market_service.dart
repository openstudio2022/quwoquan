import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/skill/loading/skill_loader.dart';
import 'package:quwoquan_app/assistant/skill/market/skill_subscription_store.dart';

class AssistantSkillMarketService {
  AssistantSkillMarketService({
    PersonalAssistantSkillLoader? loader,
    SkillSubscriptionStore? subscriptionStore,
  }) : _loader = loader ?? const PersonalAssistantSkillLoader(),
       _subscriptionStore = subscriptionStore ?? SkillSubscriptionStore();

  final PersonalAssistantSkillLoader _loader;
  final SkillSubscriptionStore _subscriptionStore;
  List<PersonalAssistantSkillInfo>? _cachedSkills;

  Future<List<PersonalAssistantSkillInfo>> listSkills() async {
    final cached = _cachedSkills;
    if (cached != null) return cached;
    return refreshSkills();
  }

  Future<List<PersonalAssistantSkillInfo>> refreshSkills() async {
    final manifests = await _loader.loadBundledSkills();
    final enabledIds = await _subscriptionStore.loadEnabledSkillIds();
    final result = manifests
        .map(
          (m) => PersonalAssistantSkillInfo(
            manifest: m,
            enabled: m.defaultEnabled || enabledIds.contains(m.id),
            source: 'bundled',
            version: m.version,
            category: m.category,
            tier: m.tier,
            isDefaultFree: m.tier == 'free' && m.defaultEnabled,
          ),
        )
        .toList(growable: false);
    _cachedSkills = result;
    return result;
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) async {
    await _subscriptionStore.setSkillEnabled(skillId, enabled);
    _cachedSkills = null;
  }
}
