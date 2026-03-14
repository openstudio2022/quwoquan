import 'package:shared_preferences/shared_preferences.dart';

class SkillSubscriptionStore {
  static const String _key = 'personal_assistant_enabled_skills';

  Future<Set<String>> loadEnabledSkillIds() async {
    final prefs = await SharedPreferences.getInstance();
    final values = prefs.getStringList(_key) ?? <String>[];
    return values.toSet();
  }

  Future<void> setSkillEnabled(String skillId, bool enabled) async {
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
