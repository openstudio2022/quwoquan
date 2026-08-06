/// SkillConsent 的本地缓存（SharedPreferences，按 accountId 物理分区）。
/// 缓存只保存当前 canonical item 列表，不携带版本信封，也不参与授权裁决。
library;

import 'dart:convert';
import 'dart:developer' as developer;

import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/skill_consent_facet.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_consent/application/public/skill_consent_terminal_account_purger.dart';
import 'package:crypto/crypto.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:shared_preferences/shared_preferences.dart';

part 'assistant_consent_success_snapshot.dart';

class AssistantConsentStore implements SkillConsentTerminalAccountPurger {
  AssistantConsentStore({required String accountId})
    : _accountId = _requireAccountId(accountId);

  final String _accountId;

  /// 在 production Remote Facet 外增加非裁决性的成功快照。
  ///
  /// 返回值和异常始终来自 [remote]；快照不会在 Remote 失败时被读取为
  /// fallback，也不能参与任何授权决策。
  static AssistantSkillConsentFacet decorateRemoteSuccess({
    required String accountId,
    required AssistantSkillConsentFacet remote,
  }) {
    return AssistantConsentSuccessSnapshotDecorator(
      remote,
      AssistantConsentStore(accountId: accountId),
    );
  }

  String get _key {
    final digest = sha256.convert(utf8.encode(_accountId)).toString();
    return 'assistant_skill_consents:$digest';
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
      if (decoded.any((item) => item is! Map)) {
        throw const FormatException(
          'Assistant consent snapshot contains a non-object item',
        );
      }
      final items = decoded
          .cast<Map>()
          .map((item) => SkillConsent.fromJson(item.cast<String, dynamic>()))
          .toList(growable: false);
      _validateActiveSnapshot(items);
      return items;
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
    _validateActiveSnapshot(items);
    final prefs = await SharedPreferences.getInstance();
    final persisted = await prefs.setString(
      _key,
      jsonEncode(items.map((item) => item.toJson()).toList(growable: false)),
    );
    if (!persisted) {
      throw StateError('assistant consent snapshot persistence failed');
    }
  }

  Future<void> upsert(SkillConsent next) async {
    _validateActiveConsent(next);
    final current = await load();
    final merged = <SkillConsent>[
      for (final item in current)
        if (item.skillId != next.skillId) item,
      next,
    ];
    await save(merged);
  }

  Future<void> revoke(String skillId) async {
    final normalizedSkillId = skillId.trim();
    if (normalizedSkillId.isEmpty) {
      throw ArgumentError.value(
        skillId,
        'skillId',
        'Assistant consent snapshot requires a non-empty skill identity',
      );
    }
    final current = await load();
    final next = current
        .where((item) => item.skillId != normalizedSkillId)
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

  @override
  Future<void> purgeForTerminalAccountClosure() =>
      clearForTerminalAccountClosure();

  void _validateGrantResponse(
    SkillConsent consent, {
    required String requestedSkillId,
    required List<String> requestedScopes,
  }) {
    _validateActiveConsent(consent);
    final normalizedSkillId = requestedSkillId.trim();
    if (normalizedSkillId.isEmpty || consent.skillId != normalizedSkillId) {
      throw const FormatException(
        'SkillConsent grant response does not match the requested skill',
      );
    }
    final expectedScopes = _canonicalScopes(requestedScopes);
    if (!_sameOrderedStrings(consent.grantedScopes, expectedScopes)) {
      throw const FormatException(
        'SkillConsent grant response does not contain the complete requested scope set',
      );
    }
  }

  void _validateActiveSnapshot(List<SkillConsent> items) {
    final skillIds = <String>{};
    for (final item in items) {
      _validateActiveConsent(item);
      if (!skillIds.add(item.skillId)) {
        throw const FormatException(
          'SkillConsent snapshot contains duplicate active skills',
        );
      }
    }
  }

  void _validateActiveConsent(SkillConsent consent) {
    if (consent.accountId != _accountId) {
      throw const FormatException(
        'SkillConsent snapshot account ownership mismatch',
      );
    }
    if (consent.id.trim().isEmpty ||
        consent.id != consent.id.trim() ||
        consent.skillId.trim().isEmpty ||
        consent.skillId != consent.skillId.trim()) {
      throw const FormatException(
        'SkillConsent snapshot identity must be canonical and non-empty',
      );
    }
    if (!consent.granted || consent.revokedAt != null) {
      throw const FormatException(
        'SkillConsent snapshot may only contain active grants',
      );
    }
    if (DateTime.tryParse(consent.grantedAt) == null) {
      throw const FormatException(
        'SkillConsent snapshot grantedAt is not a timestamp',
      );
    }
    final canonicalScopes = _canonicalScopes(consent.grantedScopes);
    if (!_sameOrderedStrings(consent.grantedScopes, canonicalScopes)) {
      throw const FormatException(
        'SkillConsent snapshot scopes are not canonical',
      );
    }
  }

  static String _requireAccountId(String accountId) {
    final normalized = accountId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(
        accountId,
        'accountId',
        'Assistant consent snapshots require an authenticated account',
      );
    }
    return normalized;
  }

  static List<String> _canonicalScopes(List<String> scopes) {
    final normalized = scopes.map((scope) => scope.trim()).toList();
    if (normalized.isEmpty || normalized.any((scope) => scope.isEmpty)) {
      throw const FormatException(
        'SkillConsent snapshot scopes must be non-empty',
      );
    }
    final unique = normalized.toSet();
    if (unique.length != normalized.length) {
      throw const FormatException(
        'SkillConsent snapshot scopes must not contain duplicates',
      );
    }
    return unique.toList()..sort();
  }

  static bool _sameOrderedStrings(List<String> left, List<String> right) {
    if (left.length != right.length) {
      return false;
    }
    for (var index = 0; index < left.length; index += 1) {
      if (left[index] != right[index]) {
        return false;
      }
    }
    return true;
  }
}
