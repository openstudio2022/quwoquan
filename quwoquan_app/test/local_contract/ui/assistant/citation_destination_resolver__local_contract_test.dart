// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/assistant/transcript/citation/assistant_citation.dart';
import 'package:quwoquan_app/assistant/transcript/citation/citation_destination_resolver.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  test('站内引用只通过 metadata 生成的 canonical object 路由解析', () {
    const destination = CitationDestination(
      kind: CitationDestinationKind.internal,
      objectTypeRef: 'content.post',
      objectId: 'post-1',
    );

    final resolved = CitationDestinationResolver.resolve(destination);

    expect(resolved, isA<InternalCitationDestination>());
    final internal = resolved! as InternalCitationDestination;
    expect(internal.routePath, '/works/browser/post-1');
    expect(internal.deepLink, 'quwoquan://content/post/post-1');
  });

  test('未知站内对象、HTTP 链接和 URL-only 引用均 fail-closed', () {
    expect(
      CitationDestinationResolver.resolve(
        const CitationDestination(
          kind: CitationDestinationKind.internal,
          objectTypeRef: 'unknown.object',
          objectId: 'id-1',
        ),
      ),
      isNull,
    );
    expect(
      CitationDestinationResolver.resolve(
        const CitationDestination(
          kind: CitationDestinationKind.external,
          url: 'http://example.com',
        ),
      ),
      isNull,
    );
    expect(
      () => AssistantCitation.fromReferenceMap(<String, dynamic>{
        'title': '旧式引用',
        'url': 'https://example.com',
      }),
      throwsFormatException,
    );
  });

  test('站外引用仅接受 HTTPS 并移除 fragment', () {
    const destination = CitationDestination(
      kind: CitationDestinationKind.external,
      url: 'https://example.com/doc#private-fragment',
    );
    final uri = Uri.tryParse(destination.url!);
    expect(uri?.scheme, 'https');
    expect(uri?.host, 'example.com');

    final resolved = CitationDestinationResolver.resolve(destination);

    expect(resolved, isA<ExternalCitationDestination>());
    expect(
      (resolved! as ExternalCitationDestination).uri.toString(),
      'https://example.com/doc',
    );
  });
}
