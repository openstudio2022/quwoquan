import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('profile interaction queries encode the canonical persona path key', () {
    final query = ContentProfileInteractionPageQuery(
      personaId: 'persona-1',
      type: InteractionActivityType.comment,
      cursor: 'cursor-1',
      limit: 9,
    );
    final received =
        encodeContentProfileInteractionActivityViewListProfileInteractionActivitiesReceivedGeneratedRequest(
          query,
        );
    final sent =
        encodeContentProfileInteractionActivityViewListProfileInteractionActivitiesSentGeneratedRequest(
          query,
        );

    for (final request in <CloudOperationRequestPayload>[received, sent]) {
      expect(request.pathParameters, <String, String>{
        'personaId': 'persona-1',
      });
      expect(request.pathParameters, isNot(contains('userId')));
      expect(request.queryParameters, <String, String>{
        'type': 'comment',
        'cursor': 'cursor-1',
        'limit': '9',
      });
    }
  });

  test('profile read facts encode the same canonical persona path key', () {
    final request =
        encodeContentProfileInteractionReadFactAppendProfileInteractionReadFactGeneratedRequest(
          AppendContentProfileInteractionReadFactCommand(
            personaId: 'persona-1',
            activityId: 'activity-1',
            state: ProfileInteractionReadState.read,
          ),
        );

    expect(request.pathParameters, <String, String>{
      'personaId': 'persona-1',
      'interactionId': 'activity-1',
    });
    expect(request.pathParameters, isNot(contains('userId')));
    expect(request.body, <String, Object?>{'state': 'read'});
  });
}
