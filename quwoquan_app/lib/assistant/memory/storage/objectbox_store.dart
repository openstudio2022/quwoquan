import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:quwoquan_app/assistant/memory/domain/vector_store.dart';
import 'package:quwoquan_app/assistant/memory/storage/assistant_storage_path.dart';

/// Lightweight ObjectBox-compatible vector store backed by a JSON file.
class ObjectBoxVectorStore implements AssistantVectorStore {
  ObjectBoxVectorStore({
    String? storagePath,
  }) : _pathFuture = storagePath != null
            ? Future<String>.value(storagePath)
            : getPersonalAssistantStoragePath('vector_store.json');

  final Future<String> _pathFuture;
  final Map<String, VectorMemoryItem> _items = <String, VectorMemoryItem>{};
  bool _loaded = false;

  @override
  Future<void> upsert(VectorMemoryItem item) async {
    await _loadIfNeeded();
    _items[item.id] = item;
    await _flush();
  }

  @override
  Future<List<VectorMemoryItem>> search(
    List<double> queryVector, {
    int limit = 5,
  }) async {
    await _loadIfNeeded();
    final scored = _items.values
        .map(
          (item) => (
            item: item,
            score: _cosine(queryVector, item.vector),
          ),
        )
        .toList(growable: false)
      ..sort((a, b) => b.score.compareTo(a.score));
    return scored.take(limit).map((entry) => entry.item).toList(growable: false);
  }

  Future<void> _loadIfNeeded() async {
    if (_loaded) return;
    _loaded = true;
    final path = await _pathFuture;
    final file = File(path);
    if (!await file.exists()) return;
    final decoded = jsonDecode(await file.readAsString());
    if (decoded is! Map) return;
    for (final entry in decoded.entries) {
      final id = entry.key.toString();
      final map = entry.value;
      if (map is! Map) continue;
      final text = map['text']?.toString() ?? '';
      final vector = (map['vector'] as List? ?? const <dynamic>[])
          .map((item) => (item as num).toDouble())
          .toList(growable: false);
      final metadata =
          (map['metadata'] as Map?)?.cast<String, dynamic>() ?? <String, dynamic>{};
      _items[id] = VectorMemoryItem(
        id: id,
        text: text,
        vector: vector,
        metadata: metadata,
      );
    }
  }

  Future<void> _flush() async {
    final path = await _pathFuture;
    final file = File(path);
    await file.parent.create(recursive: true);
    final payload = <String, dynamic>{};
    for (final entry in _items.entries) {
      payload[entry.key] = <String, dynamic>{
        'text': entry.value.text,
        'vector': entry.value.vector,
        'metadata': entry.value.metadata,
      };
    }
    await file.writeAsString(jsonEncode(payload));
  }

  double _cosine(List<double> a, List<double> b) {
    if (a.isEmpty || b.isEmpty || a.length != b.length) return 0;
    double dot = 0;
    double na = 0;
    double nb = 0;
    for (var i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      na += a[i] * a[i];
      nb += b[i] * b[i];
    }
    if (na == 0 || nb == 0) return 0;
    return dot / (math.sqrt(na) * math.sqrt(nb));
  }
}
