part of 'auth_session.dart';

// 这是端侧持久身份键一次性迁移的唯一边界。业务运行时只读写
// `auth.active_persona_id`，不做 dual-read/dual-write。
const String _retiredActivePersonaKey = 'auth.active_sub_account_id';

Future<String> _migrateActivePersonaKey(SharedPreferences preferences) async {
  final canonical =
      preferences.getString(AuthSessionStore._activePersonaIdKey)?.trim() ?? '';
  final retired =
      preferences.getString(_retiredActivePersonaKey)?.trim() ?? '';

  if (canonical.isNotEmpty && retired.isNotEmpty && canonical != retired) {
    throw StateError(
      'conflicting persisted active Persona identities; migration stopped',
    );
  }

  final resolved = canonical.isNotEmpty ? canonical : retired;
  if (canonical.isEmpty && retired.isNotEmpty) {
    final written = await preferences.setString(
      AuthSessionStore._activePersonaIdKey,
      retired,
    );
    final verified =
        preferences.getString(AuthSessionStore._activePersonaIdKey)?.trim() ==
        retired;
    if (!written || !verified) {
      throw StateError('failed to verify active Persona identity migration');
    }
  }
  await _removeRetiredActivePersonaKey(preferences);
  return resolved;
}

Future<void> _removeRetiredActivePersonaKey(
  SharedPreferences preferences,
) async {
  if (!preferences.containsKey(_retiredActivePersonaKey)) {
    return;
  }
  final removed = await preferences.remove(_retiredActivePersonaKey);
  if (!removed || preferences.containsKey(_retiredActivePersonaKey)) {
    throw StateError('failed to remove retired active Persona identity key');
  }
}
