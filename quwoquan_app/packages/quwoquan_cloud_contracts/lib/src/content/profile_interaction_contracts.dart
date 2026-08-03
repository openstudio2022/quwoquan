import 'content_operation_contracts.g.dart';

abstract interface class ContentProfileInteractionQueryFacet {
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  });
}

abstract interface class ContentProfileInteractionReadFactAppendFacet {
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  );
}
