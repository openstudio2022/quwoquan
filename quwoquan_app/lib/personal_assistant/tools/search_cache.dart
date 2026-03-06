/// In-memory TTL cache for search results.
///
/// Prevents duplicate web searches for the same (or very similar) queries
/// within a single agent run or across consecutive runs. Cache entries
/// expire after [ttl] and the cache auto-evicts the oldest entries when
/// [maxEntries] is exceeded.
class SearchResultCache {
  SearchResultCache({
    this.ttl = const Duration(minutes: 10),
    this.maxEntries = 50,
  });

  final Duration ttl;
  final int maxEntries;
  final Map<String, _CacheEntry> _cache = <String, _CacheEntry>{};

  /// Returns a cached result if one exists and hasn't expired.
  Map<String, dynamic>? get(String query) {
    final key = _normalizeKey(query);
    final entry = _cache[key];
    if (entry == null) return null;
    if (DateTime.now().difference(entry.createdAt) > ttl) {
      _cache.remove(key);
      return null;
    }
    return entry.data;
  }

  /// Stores a search result in the cache.
  void put(String query, Map<String, dynamic> data) {
    final key = _normalizeKey(query);
    _cache[key] = _CacheEntry(data: data, createdAt: DateTime.now());
    _evictIfNeeded();
  }

  /// Check if a non-expired entry exists.
  bool has(String query) => get(query) != null;

  /// Clear the entire cache (e.g. at session start).
  void clear() => _cache.clear();

  int get length => _cache.length;

  /// Normalize key: lowercase, collapse whitespace, trim.
  static String _normalizeKey(String query) {
    return query.trim().toLowerCase().replaceAll(RegExp(r'\s+'), ' ');
  }

  void _evictIfNeeded() {
    if (_cache.length <= maxEntries) return;
    final now = DateTime.now();
    _cache.removeWhere(
      (_, entry) => now.difference(entry.createdAt) > ttl,
    );
    while (_cache.length > maxEntries) {
      _cache.remove(_cache.keys.first);
    }
  }
}

class _CacheEntry {
  const _CacheEntry({required this.data, required this.createdAt});
  final Map<String, dynamic> data;
  final DateTime createdAt;
}
