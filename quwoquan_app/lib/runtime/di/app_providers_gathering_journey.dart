import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_collaboration_facets.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_content_link_port.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_guide_assignment_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_moment_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_plan_capabilities.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_query.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_share_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_template_capability.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_journey_travelogue_draft.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_publication_continuation_registry.dart';

/// Gathering Journey 的 production graph 只声明 Circle-owned typed ports。
///
/// Circle generated handoff 未交付对象级 adapter 前，解析对应能力会结构化
/// fail-fast；这里不回退到 legacy vertical Remote、fixture 或本地合成结果。
final gatheringJourneyCapabilityQueryProvider =
    Provider<GatheringJourneyCapabilityQuery>(
      (ref) => requireGatheringRemoteAdapter('GatheringJourneyCapabilityQuery'),
    );

final gatheringJourneyParticipationWriterProvider =
    Provider<GatheringJourneyParticipationWriter>(
      (ref) =>
          requireGatheringRemoteAdapter('GatheringJourneyParticipationWriter'),
    );

final gatheringJourneyPlacementQueryProvider =
    Provider<GatheringJourneyPlacementQuery>(
      (ref) => requireGatheringRemoteAdapter('GatheringJourneyPlacementQuery'),
    );

final gatheringJourneyPlacementWriterProvider =
    Provider<GatheringJourneyPlacementWriter>(
      (ref) => requireGatheringRemoteAdapter('GatheringJourneyPlacementWriter'),
    );

final gatheringJourneyContentReferenceWriterProvider =
    Provider<GatheringJourneyContentReferenceWriter>(
      (ref) => requireGatheringRemoteAdapter(
        'GatheringJourneyContentReferenceWriter',
      ),
    );

final gatheringJourneySupportAssignmentWriterProvider =
    Provider<GatheringJourneySupportAssignmentWriter>(
      (ref) => requireGatheringRemoteAdapter(
        'GatheringJourneySupportAssignmentWriter',
      ),
    );

final gatheringJourneyExperienceWriterProvider =
    Provider<GatheringJourneyExperienceWriter>(
      (ref) =>
          requireGatheringRemoteAdapter('GatheringJourneyExperienceWriter'),
    );

final gatheringPlanCommandWriterProvider = Provider<GatheringPlanCommandWriter>(
  (ref) => requireGatheringRemoteAdapter('GatheringPlanCommandWriter'),
);

final gatheringPlanQueryReaderProvider = Provider<GatheringPlanQueryReader>(
  (ref) => requireGatheringRemoteAdapter('GatheringPlanQueryReader'),
);

final gatheringJourneyQueryProvider = Provider<GatheringJourneyQuery>(
  (ref) => requireGatheringRemoteAdapter('GatheringJourneyQuery'),
);

final gatheringJourneySnapshotProvider = FutureProvider.autoDispose
    .family<GatheringJourneySnapshot, String>(
      (ref, gatheringId) =>
          ref.watch(gatheringJourneyQueryProvider).load(gatheringId),
    );

final gatheringJourneyShareSnapshotQueryProvider =
    Provider<GatheringJourneyShareSnapshotQuery>(
      (ref) =>
          requireGatheringRemoteAdapter('GatheringJourneyShareSnapshotQuery'),
    );

final gatheringJourneyShareSnapshotWriterProvider =
    Provider<GatheringJourneyShareSnapshotWriter>(
      (ref) =>
          requireGatheringRemoteAdapter('GatheringJourneyShareSnapshotWriter'),
    );

final gatheringJourneyTemplateQueryProvider =
    Provider<GatheringJourneyTemplateQuery>(
      (ref) => requireGatheringRemoteAdapter('GatheringJourneyTemplateQuery'),
    );

final gatheringJourneyTemplateWriterProvider =
    Provider<GatheringJourneyTemplateWriter>(
      (ref) => requireGatheringRemoteAdapter('GatheringJourneyTemplateWriter'),
    );

final gatheringJourneyTravelogueDraftWriterProvider =
    Provider<GatheringJourneyTravelogueDraftWriter>(
      (ref) => requireGatheringRemoteAdapter(
        'GatheringJourneyTravelogueDraftWriter',
      ),
    );

final gatheringJourneyPostPublicationContinuationRegistryProvider =
    Provider<PostPublicationContinuationRegistry>(
      (ref) => requireGatheringRemoteAdapter(
        'GatheringJourneyPostPublicationContinuationRegistry',
      ),
    );
