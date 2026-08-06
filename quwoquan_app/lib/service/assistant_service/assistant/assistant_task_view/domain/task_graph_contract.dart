enum TaskStatus {
  pending('pending'),
  inProgress('in_progress'),
  completed('completed'),
  failed('failed');

  const TaskStatus(this.wireName);

  final String wireName;
}

TaskStatus parseTaskStatus(String raw) {
  switch (raw.trim().toLowerCase()) {
    case 'in_progress':
      return TaskStatus.inProgress;
    case 'completed':
      return TaskStatus.completed;
    case 'failed':
      return TaskStatus.failed;
    default:
      return TaskStatus.pending;
  }
}

class TaskToolArgs {
  const TaskToolArgs([this.fields = const <String, Object?>{}]);

  final Map<String, Object?> fields;

  bool get isEmpty => fields.isEmpty;

  Map<String, dynamic> toJson() => _normalizeObjectMap(fields);

  factory TaskToolArgs.fromJson(Object? raw) {
    return TaskToolArgs(_normalizeObjectMap(raw));
  }
}

class TaskOutput {
  const TaskOutput([this.fields = const <String, Object?>{}]);

  final Map<String, Object?> fields;

  bool get isEmpty => fields.isEmpty;

  Map<String, dynamic> toJson() => _normalizeObjectMap(fields);

  factory TaskOutput.fromJson(Object? raw) {
    return TaskOutput(_normalizeObjectMap(raw));
  }
}

class TaskNode {
  const TaskNode({
    required this.taskId,
    required this.intentId,
    this.toolName = '',
    this.toolArgs = const TaskToolArgs(),
    this.status = TaskStatus.pending,
    this.output = const TaskOutput(),
  });

  final String taskId;
  final String intentId;
  final String toolName;
  final TaskToolArgs toolArgs;
  final TaskStatus status;
  final TaskOutput output;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'taskId': taskId,
    'intentId': intentId,
    'toolName': toolName,
    'toolArgs': toolArgs.toJson(),
    'status': status.wireName,
    'output': output.toJson(),
  };

  factory TaskNode.fromJson(Map<String, dynamic> json) {
    return TaskNode(
      taskId: (json['taskId'] as String?)?.trim() ?? '',
      intentId: (json['intentId'] as String?)?.trim() ?? '',
      toolName: (json['toolName'] as String?)?.trim() ?? '',
      toolArgs: TaskToolArgs.fromJson(json['toolArgs']),
      status: parseTaskStatus((json['status'] as String?)?.trim() ?? ''),
      output: TaskOutput.fromJson(json['output']),
    );
  }
}

class TaskGraph {
  const TaskGraph({
    this.contractId = 'task_graph',
    this.tasks = const <TaskNode>[],
  });

  final String contractId;
  final List<TaskNode> tasks;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'contractId': contractId,
    'tasks': tasks.map((item) => item.toJson()).toList(growable: false),
  };

  factory TaskGraph.fromJson(Map<String, dynamic> json) {
    return TaskGraph(
      contractId: (json['contractId'] as String?)?.trim() ?? 'task_graph',
      tasks: _taskList(json['tasks']),
    );
  }
}

List<TaskNode> _taskList(Object? value) {
  if (value is! List) {
    return const <TaskNode>[];
  }
  return value
      .whereType<Map>()
      .map((item) => TaskNode.fromJson(item.cast<String, dynamic>()))
      .where(
        (item) =>
            item.taskId.trim().isNotEmpty && item.intentId.trim().isNotEmpty,
      )
      .toList(growable: false);
}

Map<String, dynamic> _normalizeObjectMap(Object? raw) {
  if (raw is! Map) {
    return const <String, dynamic>{};
  }
  final normalized = <String, dynamic>{};
  raw.forEach((key, value) {
    final normalizedKey = key.toString().trim();
    if (normalizedKey.isEmpty) {
      return;
    }
    normalized[normalizedKey] = _normalizeObjectValue(value);
  });
  return normalized;
}

dynamic _normalizeObjectValue(Object? value) {
  if (value is Map) {
    return _normalizeObjectMap(value);
  }
  if (value is List) {
    return value.map<dynamic>(_normalizeObjectValue).toList(growable: false);
  }
  return value;
}
