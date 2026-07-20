/// Assistant 技能授权的本地缓存（SharedPreferences，按 actor 物理分区）。
///
/// 从旧 `assistant_repository.dart` 逐字迁出；行为不变。
library;

import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AssistantConsentStore {
  AssistantConsentStore({required String actorScope})
    : _actorScope = actorScope.trim().isEmpty
          ? 'unauthenticated'
          : actorScope.trim();

  final String _actorScope;
  static const int schema = 1;

  String get _key {
    final digest = sha256.convert(utf8.encode(_actorScope)).toString();
    return 'assistant_skill_consents:${digest.substring(0, 24)}';
  }

  Future<List<AssistantSkillConsent>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.trim().isEmpty) {
      return const <AssistantSkillConsent>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic> ||
          decoded['schema'] != schema ||
          decoded['items'] is! List) {
        await prefs.remove(_key);
        return const <AssistantSkillConsent>[];
      }
      return (decoded['items'] as List)
          .whereType<Map>()
          .map(
            (item) =>
                AssistantSkillConsent.fromJson(item.cast<String, dynamic>()),
          )
          .where((item) => item.skillId.isNotEmpty)
          .toList(growable: false);
    } catch (error) {
      // 本地缓存损坏时清除并按无授权处理（fail-closed），记录以便定位。
      developer.log(
        'assistant consent cache corrupted; clearing',
        name: 'AssistantConsentStore',
        error: error,
      );
      await prefs.remove(_key);
      return const <AssistantSkillConsent>[];
    }
  }

  Future<void> save(List<AssistantSkillConsent> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _key,
      jsonEncode(<String, dynamic>{
        'schema': schema,
        'items': items.map((item) => item.toJson()).toList(growable: false),
      }),
    );
  }

  Future<void> upsert(AssistantSkillConsent next) async {
    final current = await load();
    final merged = <AssistantSkillConsent>[
      for (final item in current)
        if (item.skillId != next.skillId) item,
      next,
    ];
    await save(merged);
  }

  Future<void> revoke(String skillId) async {
    final current = await load();
    final next = current
        .where((item) => item.skillId != skillId)
        .toList(growable: false);
    await save(next);
  }
}
