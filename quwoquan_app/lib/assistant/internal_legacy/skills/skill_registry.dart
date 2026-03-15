import 'package:quwoquan_app/assistant/internal_legacy/skills/skill_manifest.dart';

/// Unified skill metadata registry. Centralizes registration, indexing,
/// and lifecycle governance for all skills in the platform.
///
/// Currently backed by an in-memory map. Future versions may load from
/// a remote catalog service or on-device SQLite.
class SkillRegistry {
  SkillRegistry();

  final Map<String, _SkillEntry> _entries = <String, _SkillEntry>{};

  /// Register a skill manifest. If a skill with the same [domainId] exists,
  /// it is replaced only if the new version is higher.
  void register(PersonalAssistantSkillManifest manifest) {
    final existing = _entries[manifest.domainId];
    if (existing != null && !_isHigherVersion(manifest.version, existing.manifest.version)) {
      return;
    }
    _entries[manifest.domainId] = _SkillEntry(
      manifest: manifest,
      registeredAt: DateTime.now(),
    );
  }

  /// Bulk-register skills from a list of manifests.
  void registerAll(Iterable<PersonalAssistantSkillManifest> manifests) {
    for (final m in manifests) {
      register(m);
    }
  }

  /// Remove a skill by domain ID.
  bool unregister(String domainId) {
    return _entries.remove(domainId) != null;
  }

  /// Get a manifest by domain ID, or null.
  PersonalAssistantSkillManifest? get(String domainId) {
    return _entries[domainId]?.manifest;
  }

  /// All registered manifests, sorted by domain ID.
  List<PersonalAssistantSkillManifest> get allManifests {
    final sorted = _entries.keys.toList()..sort();
    return sorted.map((id) => _entries[id]!.manifest).toList(growable: false);
  }

  /// All registered domain IDs.
  List<String> get allDomainIds {
    final ids = _entries.keys.toList()..sort();
    return ids;
  }

  /// Number of registered skills.
  int get count => _entries.length;

  /// Whether a domain is registered.
  bool contains(String domainId) => _entries.containsKey(domainId);

  /// Retrieve skills matching a category.
  List<PersonalAssistantSkillManifest> byCategory(String category) {
    return _entries.values
        .where((e) => e.manifest.category == category)
        .map((e) => e.manifest)
        .toList(growable: false);
  }

  /// Retrieve skills matching a tier (free / pro).
  List<PersonalAssistantSkillManifest> byTier(String tier) {
    return _entries.values
        .where((e) => e.manifest.tier == tier)
        .map((e) => e.manifest)
        .toList(growable: false);
  }

  /// Clear all registered skills (useful for testing).
  void clear() => _entries.clear();

  static bool _isHigherVersion(String incoming, String existing) {
    final iParts = incoming.split('.').map(int.tryParse).toList();
    final eParts = existing.split('.').map(int.tryParse).toList();
    for (int i = 0; i < 3; i++) {
      final iv = i < iParts.length ? (iParts[i] ?? 0) : 0;
      final ev = i < eParts.length ? (eParts[i] ?? 0) : 0;
      if (iv > ev) return true;
      if (iv < ev) return false;
    }
    return false;
  }
}

class _SkillEntry {
  const _SkillEntry({
    required this.manifest,
    required this.registeredAt,
  });

  final PersonalAssistantSkillManifest manifest;
  final DateTime registeredAt;
}
