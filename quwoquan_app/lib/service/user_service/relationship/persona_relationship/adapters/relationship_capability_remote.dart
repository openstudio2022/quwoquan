import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final class RemoteRelationshipCapabilityRepository
    implements RelationshipCapabilityRepository {
  const RemoteRelationshipCapabilityRepository({required this.query});

  final RelationshipCapabilityQuery query;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => false;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    final result = await query.getRelationshipCapability(
      GetRelationshipCapabilityQuery(targetPersonaId: targetUserId),
    );
    return RelationshipCapabilityViewData.fromWire(result);
  }
}
