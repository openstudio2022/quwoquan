import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart'
    show homepageDetailSocialProofReaderProvider;
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart'
    show gatheringQueryReaderProvider;
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_ports.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/content_repository_contract.dart'
    show ContentGatheringSocialProofReader;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show GatheringSocialProofSummary;

/// Seals the two optional Remote reads mounted by Homepage source cards.
///
/// This cross-domain boundary belongs to the runtime harness rather than either
/// object-owned support tree. Individual Homepage tests may layer a typed
/// reader when source-card behavior is their subject.
List<Override> homepageSourceCardsBoundaryOverrides() => <Override>[
  gatheringQueryReaderProvider.overrideWithValue(
    const _EmptyGatheringQueryReader(),
  ),
  homepageDetailSocialProofReaderProvider.overrideWithValue(
    const _ZeroGatheringSocialProofReader(),
  ),
];

final class _EmptyGatheringQueryReader implements GatheringQueryReader {
  const _EmptyGatheringQueryReader();

  @override
  Future<GatheringDetailPresentationSlice?> getDetail(
    GatheringDetailQuery query,
  ) async => null;

  @override
  Future<List<GatheringSourceCardSummary>> listBySource(
    GatheringBySourceListQuery query,
  ) async => const <GatheringSourceCardSummary>[];

  @override
  Future<GatheringHostCardPage> listByHost(
    GatheringByHostListQuery query,
  ) async => GatheringHostCardPage.empty;

  @override
  Future<GatheringHostCardPage> listMine(GatheringMineListQuery query) async =>
      GatheringHostCardPage.empty;
}

final class _ZeroGatheringSocialProofReader
    implements ContentGatheringSocialProofReader {
  const _ZeroGatheringSocialProofReader();

  @override
  Future<GatheringSocialProofSummary> getGatheringSocialProof({
    required String anchorKind,
    required String objectId,
  }) async {
    return GatheringSocialProofSummary(
      anchorKind: anchorKind,
      objectId: objectId,
      publishedCount: 0,
      formedCount: 0,
      experiencedCount: 0,
    );
  }
}
