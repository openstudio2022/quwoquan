import 'package:quwoquan_app/core/mock/prototype_mock_data.dart';

final class AssistantPrototypeMemoryRow {
  const AssistantPrototypeMemoryRow({
    required this.memoryKey,
    required this.title,
    this.kind,
  });

  final String memoryKey;
  final String title;
  final String? kind;
}

final class AssistantPrototypeTaskRow {
  const AssistantPrototypeTaskRow({
    required this.taskKey,
    required this.title,
    this.time,
    required this.status,
    this.category,
  });

  final String taskKey;
  final String title;
  final String? time;
  final String status;
  final String? category;
}

final class AssistantPrototypeSkillRow {
  const AssistantPrototypeSkillRow({
    required this.skillId,
    required this.name,
    this.description,
  });

  final String skillId;
  final String name;
  final String? description;
}

/// Assistant alpha fixture 的强类型边界；不聚合 Chat、Circle 或 Content 数据。
final class AssistantPrototypeFixture {
  AssistantPrototypeFixture._({
    required this.memories,
    required this.tasks,
    required this.skills,
  });

  static final AssistantPrototypeFixture instance = AssistantPrototypeFixture._(
    memories: PrototypeMockData.assistantMemoryData
        .map(
          (row) => AssistantPrototypeMemoryRow(
            memoryKey: row['id']?.toString() ?? '',
            title: row['title']?.toString() ?? '',
            kind: row['type']?.toString(),
          ),
        )
        .toList(growable: false),
    tasks: PrototypeMockData.assistantTasksData
        .map(
          (row) => AssistantPrototypeTaskRow(
            taskKey: row['id']?.toString() ?? '',
            title: row['title']?.toString() ?? '',
            time: row['time']?.toString(),
            status: row['status']?.toString() ?? 'pending',
            category: row['category']?.toString(),
          ),
        )
        .toList(growable: false),
    skills: PrototypeMockData.assistantSkillsData
        .map(
          (row) => AssistantPrototypeSkillRow(
            skillId: row['id']?.toString() ?? '',
            name: row['name']?.toString() ?? '',
            description: row['desc']?.toString(),
          ),
        )
        .toList(growable: false),
  );

  final List<AssistantPrototypeMemoryRow> memories;
  final List<AssistantPrototypeTaskRow> tasks;
  final List<AssistantPrototypeSkillRow> skills;
}
