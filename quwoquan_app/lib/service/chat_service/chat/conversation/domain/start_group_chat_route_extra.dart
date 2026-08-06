/// 发起群聊页的结构化来源上下文。
///
/// 仅承载普通群聊的来源与归因；Gathering 使用独立 typed 创建请求，
/// 禁止通过本对象退化为普通建群。
class StartGroupChatRouteExtra {
  const StartGroupChatRouteExtra({
    this.actionKey = '',
    this.actionLabel = '',
    this.targetObjectId = '',
    this.targetObjectKind = '',
    this.targetObjectName = '',
    this.targetRouteId = '',
    this.intersectionId = '',
    this.dimension = '',
    this.intersectionClass = '',
    this.sourceRef = '',
    this.evidenceId = '',
  });

  final String actionKey;
  final String actionLabel;
  final String targetObjectId;
  final String targetObjectKind;

  /// 共同对象的渲染名（来自云侧主句 span，如「老君山」去掉书名号）。
  ///
  /// 从对象上下文发起普通群聊时用它命名新群；
  /// 拿不到名字时退回成员名拼接，不用 objectId 当名字。
  final String targetObjectName;
  final String targetRouteId;
  final String intersectionId;
  final String dimension;
  final String intersectionClass;
  final String sourceRef;
  final String evidenceId;

  bool get hasCompanionContext =>
      targetObjectId.trim().isNotEmpty || sourceRef.trim().isNotEmpty;

  String get safeTargetObjectId => targetObjectId.trim();
  String get safeTargetObjectKind => targetObjectKind.trim();
  String get safeTargetObjectName => targetObjectName.trim();
  String get safeSourceRef => sourceRef.trim();

  Map<String, dynamic> toAnalyticsPayload() {
    final payload = <String, dynamic>{};
    void putIfNotEmpty(String key, String value) {
      final trimmed = value.trim();
      if (trimmed.isNotEmpty) {
        payload[key] = trimmed;
      }
    }

    putIfNotEmpty('actionKey', actionKey);
    putIfNotEmpty('actionLabel', actionLabel);
    putIfNotEmpty('targetObjectId', targetObjectId);
    putIfNotEmpty('targetObjectKind', targetObjectKind);
    putIfNotEmpty('targetObjectName', targetObjectName);
    putIfNotEmpty('targetRouteId', targetRouteId);
    putIfNotEmpty('intersectionId', intersectionId);
    putIfNotEmpty('intersectionDimension', dimension);
    putIfNotEmpty('intersectionClass', intersectionClass);
    putIfNotEmpty('intersectionSourceRef', sourceRef);
    putIfNotEmpty('intersectionEvidenceId', evidenceId);
    return payload;
  }
}
