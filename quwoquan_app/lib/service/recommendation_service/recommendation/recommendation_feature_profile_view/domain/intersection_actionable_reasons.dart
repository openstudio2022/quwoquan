import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 可行动交集展示分层（REQ-008 可约分组）。
///
/// 判定事实全部来自云侧下发字段：`actionHints` 非空 + `expiresAt` 为空或未到期 +
/// `intersectionClass == fact`。端侧只做展示分层，不重排组内顺序、不本地拼句、
/// 不推断任何云侧未声明的可行动性（诚实红线：可行动 = 云侧已给出可兑现行动）。

/// 单条交集是否可行动。[now] 仅用于测试注入确定性时钟，生产缺省取当前 UTC。
bool isActionableIntersectionReason(IntersectionReason reason, {DateTime? now}) {
  if (reason.intersectionClass != 'fact') {
    return false;
  }
  if (reason.actionHints.isEmpty) {
    return false;
  }
  final expiresRaw = reason.expiresAt.trim();
  if (expiresRaw.isEmpty) {
    return true;
  }
  final expires = DateTime.tryParse(expiresRaw);
  if (expires == null) {
    // 无法解析的过期时间按已过期处理：宁可少置顶，不虚假承诺行动窗口。
    return false;
  }
  return expires.isAfter((now ?? DateTime.now()).toUtc());
}

/// 从列表中筛出可行动交集，保持输入顺序（云侧排序主权）。
List<IntersectionReason> actionableIntersectionReasons(
  List<IntersectionReason> items, {
  DateTime? now,
}) {
  final clock = (now ?? DateTime.now()).toUtc();
  return items
      .where((item) => isActionableIntersectionReason(item, now: clock))
      .toList(growable: false);
}

/// 可行动行的主行动：首个 `isPrimary` hint，缺省回落第一个 hint。
/// label 与 dispatch 均由云侧下发（actionHint 文案与 dispatch 一致的红线），
/// 端侧不改写文案、不造第二套行动分类。
IntersectionActionHint? primaryIntersectionActionHint(
  IntersectionReason reason,
) {
  if (reason.actionHints.isEmpty) {
    return null;
  }
  for (final hint in reason.actionHints) {
    if (hint.isPrimary) {
      return hint;
    }
  }
  return reason.actionHints.first;
}
