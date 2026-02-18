import 'package:quwoquan_app/personal_assistant/memory/vector_store.dart';

enum AssistentMemoryTier {
  stm,
  mtm,
  ltm,
}

class AssistentMemoryRecord {
  const AssistentMemoryRecord({
    required this.id,
    required this.tier,
    required this.text,
    required this.metadata,
    required this.createdAt,
  });

  final String id;
  final AssistentMemoryTier tier;
  final String text;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;
}

class AssistentMemoryHub {
  AssistentMemoryHub(this._vectorStore);

  final AssistantVectorStore _vectorStore;
  final Map<String, AssistentMemoryRecord> _records = <String, AssistentMemoryRecord>{};

  Future<void> remember({
    required String id,
    required AssistentMemoryTier tier,
    required String text,
    required List<double> vector,
    Map<String, dynamic> metadata = const <String, dynamic>{},
  }) async {
    _records[id] = AssistentMemoryRecord(
      id: id,
      tier: tier,
      text: text,
      metadata: metadata,
      createdAt: DateTime.now(),
    );
    await _vectorStore.upsert(
      VectorMemoryItem(
        id: id,
        text: text,
        vector: vector,
        metadata: <String, dynamic>{
          ...metadata,
          'tier': tier.name,
        },
      ),
    );
  }

  List<AssistentMemoryRecord> listByTier(AssistentMemoryTier tier) {
    return _records.values.where((record) => record.tier == tier).toList(growable: false);
  }
}

