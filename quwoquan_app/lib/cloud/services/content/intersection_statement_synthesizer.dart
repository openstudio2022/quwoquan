import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_kind_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_target.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/services/content/intersection_kind_mapping.dart';

/// 交集句式合成器（云侧 G2 模拟，端不在 UI 拼装）。
///
/// 从 `intersection_fact_items.dart` 抽出（R03 体量收敛）：按 kind 闭集模板把紧凑事实
/// 切成「代表人在数字前」的结构化富文本 span。对象类型 / 路由由 codegen 下发的
/// [IntersectionKindMetadata] / [intersectionRouteIdForObjectKind] 提供，共同数由
/// [intersectionMutualCountOf] 提供。归一编排仍在 `intersection_fact_items.dart`。

/// 按 kind 闭集模板生成「代表人在数字前」结构化富文本（G2 模拟，端不在 UI 拼装）。
///
/// 句式真相：与既有 fixture primaryText 同形（评审一致），但把代表人 / 数字 / 对象切成
/// 可点 span。数字前可点代表人（纯文本蓝字）仅当 fixture/云侧给出与对象不同的可见 person。
List<IntersectionTextSpan> buildInboxStatementSpans(
  IntersectionReason reason,
  String kind,
) {
  final n = intersectionMutualCountOf(reason);
  final objectName = reason.displayName.trim();
  final objectId = reason.actionTargetId.trim();
  final objectKind = reason.objectKind.trim().isNotEmpty
      ? reason.objectKind.trim()
      : (IntersectionKindMetadata.of(kind)?.objectKind ?? '');
  final dimension = reason.dimension.trim();
  final objectSpan = _objectSpanOf(objectName, objectId, objectKind);

  // 与对象不同的可见 person 代表人（隐私态非 visible 不外显具体名字）。
  final repActor = reason.representativeActor;
  final hasDistinctRep =
      repActor != null &&
      repActor.actorId.trim().isNotEmpty &&
      repActor.displayName.trim().isNotEmpty &&
      repActor.actorId.trim() != objectId &&
      (repActor.privacyState.trim().isEmpty ||
          repActor.privacyState.trim() == 'visible');
  final repName = hasDistinctRep ? repActor.displayName.trim() : '';
  final repId = hasDistinctRep ? repActor.actorId.trim() : '';

  switch (kind) {
    // 数字指人、代表人在数字前：[lead][rep 等?][N][verb][object]。
    case 'sharedFollowees':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你关注的', verb: '人也关注了');
    case 'coCommented':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都讨论过');
    case 'sharedDiscussion':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都在', tail: '发言');
    case 'coSharedContent':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都转发过');
    case 'coLiked':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都赞过');
    case 'coVisitedEntity':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都去过');
    case 'sharedEntityAttention':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都关注');
    case 'sharedCircle':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人同在');
    case 'coMemberCircle':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都活跃在');
    case 'sameSchool':
    case 'sameDepartment':
    case 'sameMajor':
    case 'sameCohort':
    case 'alumni':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '位校友都来自');
    case 'sameCompany':
    case 'sameTeam':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '位同事都在');
    case 'sameIndustry':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '位同行都做过');

    // 桥接型：你关注的 N 人 {verb} 对象。
    case 'followeeInObject':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你关注的', verb: '人在');
    case 'followeeVisited':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你关注的', verb: '人来过');
    case 'followeeViewing':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你关注的', verb: '人正在看');
    case 'followeeDiscussedThis':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你关注的', verb: '人在讨论');
    case 'alumniHere':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你的', verb: '位校友也在');
    case 'colleagueHere':
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你的', verb: '位同事也在');

    // 对象是人、数字在后：你和 [object-person] 有 N 位共同…。
    case 'commonFollower':
      return _objectThenCount(objectSpan, objectName, n, dimension,
          mid: '有', tail: '位共同关注者');
    case 'commonContact':
      return _objectThenCount(objectSpan, objectName, n, dimension,
          mid: '有', tail: '位共同联系人');

    // 共同兴趣标签：代表人 + 标签（无数字）。
    case 'sharedTagSample':
      if (repName.isNotEmpty) {
        return <IntersectionTextSpan>[
          _plain('你和'),
          _personSpan(repName, repId),
          _plain('都关注'),
          objectSpan,
        ];
      }
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都关注');

    // 概率推荐：你可能和 [object] 兴趣相投。
    case 'affinity':
      if (objectName.isEmpty) return const <IntersectionTextSpan>[];
      return <IntersectionTextSpan>[
        _plain('你可能和'),
        objectSpan,
        _plain('兴趣相投'),
      ];

    default:
      if (objectName.isEmpty) return const <IntersectionTextSpan>[];
      return _countLed(repName, repId, n, dimension, objectSpan, objectName,
          lead: '你和', verb: '人都与', tail: '有关');
  }
}

/// 数字前式：`[lead]([rep]等)?[N][verb][object][tail]`，代表人恒在数字前。
List<IntersectionTextSpan> _countLed(
  String repName,
  String repId,
  int n,
  String dimension,
  IntersectionTextSpan objectSpan,
  String objectName, {
  required String lead,
  required String verb,
  String tail = '',
}) {
  if (objectName.isEmpty) return const <IntersectionTextSpan>[];
  final spans = <IntersectionTextSpan>[_plain(lead)];
  if (repName.isNotEmpty) {
    spans
      ..add(_personSpan(repName, repId))
      ..add(_plain('等'));
  }
  spans
    ..add(_countSpan(n, dimension))
    ..add(_plain(verb))
    ..add(objectSpan);
  if (tail.isNotEmpty) spans.add(_plain(tail));
  return spans;
}

/// 对象在前式：`你和[object][mid][N][tail]`（对象本身是人、数字落在末尾）。
List<IntersectionTextSpan> _objectThenCount(
  IntersectionTextSpan objectSpan,
  String objectName,
  int n,
  String dimension, {
  required String mid,
  required String tail,
}) {
  if (objectName.isEmpty) return const <IntersectionTextSpan>[];
  return <IntersectionTextSpan>[
    _plain('你和'),
    objectSpan,
    _plain(mid),
    _countSpan(n, dimension),
    _plain(tail),
  ];
}

IntersectionTextSpan _personSpan(String name, String id) {
  if (id.isEmpty) return _plain(name);
  return IntersectionTextSpan(
    text: name,
    role: 'object',
    target: IntersectionTarget(
      objectId: id,
      objectKind: 'person',
      routeId: 'userProfile',
    ),
  );
}

IntersectionTextSpan _objectSpanOf(String name, String id, String objectKind) {
  final routeId = intersectionRouteIdForObjectKind(objectKind);
  // 无 id 或无可导航 route（如 tag/content）时渲染纯文本，避免不可点的死蓝字。
  if (id.isEmpty || routeId.isEmpty) return _plain(name);
  return IntersectionTextSpan(
    text: name,
    role: 'object',
    target: IntersectionTarget(
      objectId: id,
      objectKind: objectKind,
      routeId: routeId,
    ),
  );
}

IntersectionTextSpan _countSpan(int n, String dimension) {
  return IntersectionTextSpan(
    text: '$n',
    role: 'count',
    target: IntersectionTarget(objectId: dimension, routeId: 'myIntersections'),
  );
}

IntersectionTextSpan _plain(String text) =>
    IntersectionTextSpan(text: text, role: 'plain');
