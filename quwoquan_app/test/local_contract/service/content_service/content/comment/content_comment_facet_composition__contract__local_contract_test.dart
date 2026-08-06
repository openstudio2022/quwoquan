import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/content_facet_overrides.dart';
import '../../../../../support/service/content_service/content/comment/in_memory_content_comment_facet.dart';
import '../../../../../support/service/content_service/content/post/mock_content_repository.dart';

void main() {
  test('组合根按 Comment facet 装配直连 adapter', () {
    final container = ProviderContainer(
      overrides: [
        ...mockContentFacetOverrides(
          MockContentRepository(),
          commentFacet: InMemoryContentCommentFacet(),
        ),
      ],
    );
    addTearDown(container.dispose);

    expect(
      container.read(workBrowserContentCommentFacetProvider),
      isA<ContentCommentFacet>(),
    );
  });
}
