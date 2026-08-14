// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-002.t1
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('production Search result composition uses persisted GraphQL only', () {
    final composition = File(
      'lib/runtime/di/search_dependencies.dart',
    ).readAsStringSync();
    final provider = File(
      'lib/runtime/di/app_providers_chat_search.dart',
    ).readAsStringSync();
    final remote = File(
      'lib/service/search_service/search/search_index_view/adapters/search_page_query_remote.dart',
    ).readAsStringSync();

    expect(composition, contains('GeneratedSearchPageGraphQLClient'));
    expect(composition, contains('RemoteSearchPageQuery'));
    expect(composition, isNot(contains('RemoteCanonicalSearchQuery(')));
    expect(provider, contains('generatedSearchPageGraphQLClientProvider'));
    expect(remote, contains('client.searchPage('));
    expect(remote, isNot(contains('searchSearchIndexViewSearch')));
    expect(remote, isNot(contains("'/search'")));
    expect(remote, isNot(contains("'query'")));
  });
}
