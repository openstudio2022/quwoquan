import 'package:shared_preferences/shared_preferences.dart';

class SkillSubscriptionStore {
  static const String _key = 'personal_assistant_enabled_skills';
  static const Set<String> _defaultAlwaysEnabled = <String>{
    'knowledge_qa',
    'web.quick_search',
  };

  Future<Set<String>> loadEnabledSkillIds() async {
    final prefs = await SharedPreferences.getInstance();
    final values = prefs.getStringList(_key) ?? <String>[];
    return <String>{...values, ..._defaultAlwaysEnabled};
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) async {
    if (_defaultAlwaysEnabled.contains(skillId) && !enabled) {
      // Default free skills cannot be disabled.
      return;
    }
    final prefs = await SharedPreferences.getInstance();
    final current = (prefs.getStringList(_key) ?? <String>[]).toSet();
    if (enabled) {
      current.add(skillId);
    } else {
      current.remove(skillId);
    }
    await prefs.setStringList(_key, current.toList(growable: false));
  }
}
