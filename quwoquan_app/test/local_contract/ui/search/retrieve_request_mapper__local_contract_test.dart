import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/services/retrieve_request.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

void main() {
  group('RetrieveRequest.fromSearchRequest', () {
    test(
      'maps content post + content types to article/photo/video targets',
      () {
        final request = SearchRequest(
          query: '四川 露营 攻略',
          mode: SearchMode.result,
          objectTypes: const <SearchObjectType>{SearchObjectType.contentPost},
          contentTypes: const <SearchContentTypeFilter>{
            SearchContentTypeFilter.article,
            SearchContentTypeFilter.image,
          },
        );

        final retrieve = RetrieveRequest.fromSearchRequest(request);

        expect(retrieve.targets, contains(RetrieveTarget.article));
        expect(retrieve.targets, contains(RetrieveTarget.photo));
        expect(retrieve.targets, isNot(contains(RetrieveTarget.video)));
        // terms keep the whole query plus split tokens.
        expect(retrieve.terms.first, '四川 露营 攻略');
        expect(retrieve.terms, containsAll(<String>['四川', '露营', '攻略']));
      },
    );

    test('maps chat object types to a single chat target', () {
      final request = SearchRequest(
        query: '集合时间',
        mode: SearchMode.suggest,
        objectTypes: const <SearchObjectType>{
          SearchObjectType.chatContact,
          SearchObjectType.chatConversation,
          SearchObjectType.chatMessage,
        },
      );

      final retrieve = RetrieveRequest.fromSearchRequest(request);

      expect(retrieve.targets, <RetrieveTarget>[RetrieveTarget.chat]);
    });

    test('drops non-business object types (web/tag/location)', () {
      final request = SearchRequest(
        query: '川西',
        mode: SearchMode.result,
        objectTypes: const <SearchObjectType>{
          SearchObjectType.webDocument,
          SearchObjectType.tag,
          SearchObjectType.integrationLocationPoi,
          SearchObjectType.entityHomepage,
        },
      );

      final retrieve = RetrieveRequest.fromSearchRequest(request);

      expect(retrieve.targets, <RetrieveTarget>[RetrieveTarget.entity]);
    });

    test('toMap never emits forbidden fields', () {
      final request = SearchRequest(
        query: '露营',
        mode: SearchMode.result,
        objectTypes: const <SearchObjectType>{SearchObjectType.contentPost},
      );

      final map = RetrieveRequest.fromSearchRequest(request).toMap();

      for (final forbidden in RetrieveToolContract.forbiddenFields) {
        expect(
          map.containsKey(forbidden),
          isFalse,
          reason: 'forbidden field "$forbidden" leaked into retrieve request',
        );
      }
      expect(map['targets'], isA<List<dynamic>>());
      expect(map.containsKey('terms'), isTrue);
    });

    test('retrievePayloadIsContractClean rejects forbidden keys', () {
      expect(
        retrievePayloadIsContractClean(<String, dynamic>{'title': 'ok'}),
        isTrue,
      );
      expect(
        retrievePayloadIsContractClean(<String, dynamic>{'mode': 'result'}),
        isFalse,
      );
    });
  });
}
