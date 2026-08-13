import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

/// 「我的行动」host 本人私有读面（REQ-008 / OPEN-008 收口）：消费
/// `ListMyHostedGatherings`，含 draft 与全部 audiencePolicy（invite-only /
/// unlisted 的发起人视角不再缺席）；host 身份由服务端从受信 persona 解析。
///
/// 失败与加载由消费方按 async 三态处理：主页入口降级为纯入口行（不阻塞首屏、
/// 不伪造空态），分组页展示结构化错误态 + 重试。
final myGatheringsProvider = FutureProvider.autoDispose
    .family<GatheringHostCardPage, String>((ref, personaId) async {
      if (personaId.trim().isEmpty) {
        return GatheringHostCardPage.empty;
      }
      return ref
          .watch(gatheringQueryReaderProvider)
          .listMine(const GatheringMineListQuery());
    });

/// 「我的行动」分组闭集（分组事实只由云侧 lifecycleStatus × temporalPhase 派生，
/// 端不做时间推断）。
enum MyGatheringsSegment {
  /// published 且 temporalPhase ∈ {upcoming, in_progress}。
  upcoming('upcoming'),

  /// draft（仅私有读面可见；发起人待发布草稿）。
  draft('draft'),

  /// completed，或 published 且 temporalPhase == ended。
  ended('ended'),

  /// cancelled。
  cancelled('cancelled');

  const MyGatheringsSegment(this.wireValue);

  final String wireValue;

  static MyGatheringsSegment fromQueryValue(String? value) {
    final normalized = (value ?? '').trim();
    for (final segment in MyGatheringsSegment.values) {
      if (segment.wireValue == normalized) {
        return segment;
      }
    }
    return MyGatheringsSegment.upcoming;
  }
}

/// 单卡分组归属；未识别的 lifecycle（防御）归入 ended，不渲染进行中假象。
MyGatheringsSegment myGatheringsSegmentOf(GatheringHostCardSummary card) {
  switch (card.lifecycleStatusWire) {
    case 'draft':
      return MyGatheringsSegment.draft;
    case 'cancelled':
      return MyGatheringsSegment.cancelled;
    case 'published':
      return card.temporalPhaseWire == 'ended'
          ? MyGatheringsSegment.ended
          : MyGatheringsSegment.upcoming;
    case 'completed':
    default:
      return MyGatheringsSegment.ended;
  }
}
