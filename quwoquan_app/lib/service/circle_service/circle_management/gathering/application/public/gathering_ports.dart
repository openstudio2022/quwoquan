import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';

abstract interface class GatheringCommandWriter {
  Future<GatheringCommandResult> createDraft(GatheringCreateDraftInput input);

  Future<GatheringCommandResult> publish(GatheringVersionCommandInput input);

  Future<GatheringCommandResult> update(GatheringUpdateInput input);

  Future<GatheringCommandResult> joinOpen(
    GatheringParticipationCommandInput input,
  );

  Future<GatheringCommandResult> apply(GatheringApplyInput input);

  Future<GatheringCommandResult> acceptInvitation(
    GatheringParticipationCommandInput input,
  );

  Future<GatheringCommandResult> declineInvitation(
    GatheringParticipationCommandInput input,
  );

  Future<GatheringCommandResult> watchAvailability(
    GatheringAvailabilityWatchCommandInput input,
  );

  Future<GatheringCommandResult> reviewApplication(
    GatheringReviewApplicationInput input,
  );

  Future<GatheringCommandResult> invite(GatheringInviteInput input);

  Future<GatheringCommandResult> removeParticipant(
    GatheringRemoveParticipantInput input,
  );

  Future<GatheringCommandResult> changeCapacity(
    GatheringChangeCapacityInput input,
  );

  Future<GatheringCommandResult> changeAdmission(
    GatheringChangeAdmissionInput input,
  );

  Future<GatheringCommandResult> cancel(GatheringReasonCommandInput input);

  Future<GatheringCommandResult> start(GatheringVersionCommandInput input);

  Future<GatheringCommandResult> recordOutcome(
    GatheringOutcomeCommandInput input,
  );
}

abstract interface class GatheringQueryReader {
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  );

  /// 按 canonical 来源对象（homepage/post/circle）读取公开行动卡（发布态）。
  Future<List<GatheringSourceCardSummary>> listBySource(
    GatheringBySourceListQuery query,
  );

  /// 按 Host canonical identity 读取公开披露行动 typed page（REQ-008 我的行动）。
  /// 只返回 audiencePolicy=public 的 published/cancelled/completed 行动。
  Future<GatheringHostCardPage> listByHost(GatheringByHostListQuery query);

  /// Host 本人私有全量列表（REQ-008 / OPEN-008 收口）：含 draft 与全部
  /// audiencePolicy，host 身份由服务端从受信 persona actor 解析。
  Future<GatheringHostCardPage> listMine(GatheringMineListQuery query);
}

/// Host 本人私有列表查询（App 侧输入模型；limit 上限由契约裁定）。
final class GatheringMineListQuery {
  const GatheringMineListQuery({this.cursor = '', this.limit = 20});

  final String cursor;
  final int limit;
}

/// Host 公开行动列表查询（App 侧输入模型；limit 上限由契约裁定）。
final class GatheringByHostListQuery {
  const GatheringByHostListQuery({
    required this.hostSubjectKind,
    required this.hostSubjectId,
    this.cursor = '',
    this.limit = 20,
  });

  /// 契约 `GatheringHostSubjectKind` wire 值（persona / entity_homepage / circle）。
  final String hostSubjectKind;
  final String hostSubjectId;
  final String cursor;
  final int limit;
}

/// 来源对象公开行动列表查询（App 侧输入模型；limit 上限由契约裁定）。
final class GatheringBySourceListQuery {
  const GatheringBySourceListQuery({
    required this.sourceObjectTypeRef,
    required this.sourceObjectId,
    this.limit = 3,
  });

  final String sourceObjectTypeRef;
  final String sourceObjectId;
  final int limit;
}
