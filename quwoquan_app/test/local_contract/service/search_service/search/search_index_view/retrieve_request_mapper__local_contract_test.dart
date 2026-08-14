// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002.t3
// assistant retrieval 内部口：RetrieveRequest 不得泄漏 mode 等 App 结果页字段。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/search_service/search/search_index_view/application/retrieve_request.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('RetrieveRequest contract', () {
    test('toMap never emits forbidden fields', () {
      const request = RetrieveRequest(
        targets: <RetrieveTarget>[RetrieveTarget.article],
        terms: <String>['露营'],
      );

      final map = request.toMap();

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
