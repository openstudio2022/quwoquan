/// Assistant 技能授权的本地缓存（SharedPreferences，按 accountId 物理分区）。
/// 缓存只保存当前 canonical item 列表，不携带版本信封，也不参与授权裁决。
library;

import 'dart:convert';
import 'dart:developer' as developer;

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AssistantConsentStore {
  AssistantConsentStore({required String accountId})
    : _accountId = accountId.trim().isEmpty
          ? 'unauthenticated'
          : accountId.trim();

  final String _accountId;

  String get _key {
    final digest = sha256.convert(utf8.encode(_accountId)).toString();
    return 'assistant_skill_consents:${digest.substring(0, 24)}';
  }

  Future<List<SkillConsent>> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.trim().isEmpty) {
      return const <SkillConsent>[];
    }
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) {
        await prefs.remove(_key);
        return const <SkillConsent>[];
      }
      return decoded
          .whereType<Map>()
          .map((item) => SkillConsent.fromJson(item.cast<String, dynamic>()))
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
      return const <SkillConsent>[];
    }
  }

  Future<void> save(List<SkillConsent> items) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(
      _key,
      jsonEncode(items.map((item) => item.toJson()).toList(growable: false)),
    );
  }

  Future<void> upsert(SkillConsent next) async {
    final current = await load();
    final merged = <SkillConsent>[
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

  Future<void> clearForTerminalAccountClosure() async {
    final preferences = await SharedPreferences.getInstance();
    await preferences.remove(_key);
    if (preferences.containsKey(_key)) {
      throw StateError('assistant consent cleanup verification failed');
    }
  }
}
