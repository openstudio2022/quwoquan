/// 发起群聊页的结构化来源上下文。
///
/// `start_gathering` 不能退化成无语义的普通建群：进入承接页时必须携带
/// 交集对象、actionKey 与归因字段，供页面展示、安全门、观测和后续服务契约消费。
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
  /// 建群时用它命名新群，让「拉群约伴」产生的群确实是关于这个对象的；
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
