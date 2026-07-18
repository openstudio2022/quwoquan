import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Alpha runner 专用的强类型 CircleGroup fixture。
final class AlphaCircleGroupFacet
    implements CircleGroupCommandWriter, CircleGroupQueryReader {
  final Map<String, CircleGroupSlice> _groups = <String, CircleGroupSlice>{};
  int _sequence = 0;

  @override
  Future<CircleGroupCommandResult> create(
    CreateCircleGroupCommand command,
  ) async {
    final groupId = 'alpha_group_${++_sequence}';
    final group = CircleGroupSlice(
      groupId: groupId,
      version: 1,
      circleId: command.circleId,
      parentGroupId: command.parentGroupId,
      groupType: command.groupType,
      nodeType: command.nodeType,
      name: command.name,
      description: command.description,
      visibility: command.visibility,
      joinPolicy: command.joinPolicy,
      conversationId: 'alpha_conversation_$groupId',
      storageEnabled: command.storageEnabled,
      noticeEnabled: command.noticeEnabled,
      isDefaultPublicGroup: false,
      status: CircleGroupStatus.active,
      memberCount: 1,
      createdAt: _now,
      updatedAt: _now,
    );
    _groups[_key(command.circleId, groupId)] = group;
    return _result(group);
  }

  @override
  Future<CircleGroupCommandResult> update(
    UpdateCircleGroupCommand command,
  ) async {
    final key = _key(command.circleId, command.groupId);
    final current = _required(key, command.expectedVersion);
    final updated = CircleGroupSlice(
      groupId: current.groupId,
      version: current.version + 1,
      circleId: current.circleId,
      parentGroupId: command.parentGroupId == null
          ? current.parentGroupId
          : command.parentGroupId!.isEmpty
          ? null
          : command.parentGroupId,
      groupType: current.groupType,
      nodeType: command.nodeType ?? current.nodeType,
      name: command.name ?? current.name,
      description: command.description ?? current.description,
      visibility: command.visibility ?? current.visibility,
      joinPolicy: command.joinPolicy ?? current.joinPolicy,
      conversationId: current.conversationId,
      storageEnabled: command.storageEnabled ?? current.storageEnabled,
      noticeEnabled: command.noticeEnabled ?? current.noticeEnabled,
      isDefaultPublicGroup: current.isDefaultPublicGroup,
      status: current.status,
      memberCount: current.memberCount,
      createdAt: current.createdAt,
      updatedAt: _now,
    );
    _groups[key] = updated;
    return _result(updated);
  }

  @override
  Future<CircleGroupCommandResult> archive(
    ArchiveCircleGroupCommand command,
  ) async {
    final key = _key(command.circleId, command.groupId);
    final current = _required(key);
    if (current.status == CircleGroupStatus.archived) {
      return _result(current);
    }
    final archived = _copy(
      current,
      version: current.version + 1,
      status: CircleGroupStatus.archived,
    );
    _groups[key] = archived;
    return _result(archived);
  }

  @override
  Future<CircleGroupSlice> get(CircleGroupQuery query) async {
    _ensureDefault(query.circleId);
    return _required(_key(query.circleId, query.groupId));
  }

  @override
  Future<CircleGroupPageSlice> list(CircleGroupListQuery query) async {
    _ensureDefault(query.circleId);
    final items = _groups.values
        .where((group) => group.circleId == query.circleId)
        .where(
          (group) =>
              query.groupType == null || group.groupType == query.groupType,
        )
        .where(
          (group) =>
              query.visibility == null || group.visibility == query.visibility,
        )
        .where(
          (group) =>
              query.parentGroupId == null ||
              group.parentGroupId == query.parentGroupId,
        )
        .where(
          (group) => query.nodeType == null || group.nodeType == query.nodeType,
        )
        .take(query.limit)
        .toList(growable: false);
    return CircleGroupPageSlice(items: items);
  }

  @override
  Future<CircleGroupPageSlice> search(CircleGroupSearchQuery query) async {
    final page = await list(
      CircleGroupListQuery(
        circleId: query.circleId,
        groupType: query.groupType,
        visibility: query.visibility,
        limit: query.limit,
      ),
    );
    final term = query.query.toLowerCase();
    return CircleGroupPageSlice(
      items: page.items
          .where(
            (group) =>
                group.name.toLowerCase().contains(term) ||
                group.description.toLowerCase().contains(term),
          )
          .toList(growable: false),
    );
  }

  void _ensureDefault(String circleId) {
    final groupId = 'alpha_default_$circleId';
    final key = _key(circleId, groupId);
    if (_groups.containsKey(key)) return;
    _groups[key] = CircleGroupSlice(
      groupId: groupId,
      version: 1,
      circleId: circleId,
      parentGroupId: null,
      groupType: CircleGroupType.publicGroup,
      nodeType: null,
      name: '默认公共群',
      description: 'Alpha 强类型 CircleGroup fixture',
      visibility: CircleGroupVisibility.public,
      joinPolicy: CircleGroupJoinPolicy.applyOnly,
      conversationId: 'alpha_conversation_$groupId',
      storageEnabled: true,
      noticeEnabled: true,
      isDefaultPublicGroup: true,
      status: CircleGroupStatus.active,
      memberCount: 1,
      createdAt: _now,
      updatedAt: _now,
    );
  }

  CircleGroupSlice _required(String key, [int? expectedVersion]) {
    final group = _groups[key];
    if (group == null) throw StateError('alpha CircleGroup not found');
    if (expectedVersion != null && group.version != expectedVersion) {
      throw StateError('alpha CircleGroup version conflict');
    }
    return group;
  }

  CircleGroupCommandResult _result(CircleGroupSlice group) =>
      CircleGroupCommandResult(
        groupId: group.groupId,
        version: group.version,
        status: group.status,
        idempotentReplay: false,
      );

  CircleGroupSlice _copy(
    CircleGroupSlice group, {
    required int version,
    required CircleGroupStatus status,
  }) => CircleGroupSlice(
    groupId: group.groupId,
    version: version,
    circleId: group.circleId,
    parentGroupId: group.parentGroupId,
    groupType: group.groupType,
    nodeType: group.nodeType,
    name: group.name,
    description: group.description,
    visibility: group.visibility,
    joinPolicy: group.joinPolicy,
    conversationId: group.conversationId,
    storageEnabled: group.storageEnabled,
    noticeEnabled: group.noticeEnabled,
    isDefaultPublicGroup: group.isDefaultPublicGroup,
    status: status,
    memberCount: group.memberCount,
    createdAt: group.createdAt,
    updatedAt: _now,
  );

  String _key(String circleId, String groupId) => '$circleId::$groupId';
  DateTime get _now => DateTime.utc(2026, 7, 14);
}
