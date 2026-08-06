// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/citation_destination_resolver.dart';
import 'package:quwoquan_app/runtime/di/navigation/citation_destination_navigation_mapper.dart';

void main() {
  test('站内 citation identity 只映射 metadata 生成的 route 与 deep link', () {
    const destination = InternalCitationDestination(
      objectTypeRef: 'content.post',
      objectId: 'post-1',
    );

    final resolved = CitationDestinationNavigationMapper.resolveInternal(
      destination,
    );

    expect(resolved, isNotNull);
    expect(resolved!.routePath, '/works/browser/post-1');
    expect(resolved.deepLink, 'quwoquan://content/post/post-1');
  });

  test('未登记的 object type 无导航 fallback', () {
    const destination = InternalCitationDestination(
      objectTypeRef: 'unknown.object',
      objectId: 'id-1',
    );

    expect(
      CitationDestinationNavigationMapper.resolveInternal(destination),
      isNull,
    );
  });
}
