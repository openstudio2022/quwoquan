// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-003
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/post_collection.g.dart';
import 'package:quwoquan_app/service/content_service/content/post_collection/adapters/post_collection_remote.dart';

class _Executor implements CloudOperationExecutor {
  Object? response;
  Object? failure;
  CloudOperationContract? operation;
  CloudOperationInvocationContext? invocation;
  CloudOperationRequestPayload? payload;
  int calls = 0;
  @override
  Future<T> send<T>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<T> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    calls++;
    this.operation = operation;
    invocation = context;
    payload = requestEncoder();
    if (failure != null) throw failure!;
    return responseDecoder(response);
  }
}

Map<String, Object?> _page() => {
  'collectionId': 'c',
  'ownerPersonaId': 'owner',
  'name': '合集',
  'coverAssetId': null,
  'visibility': 'public',
  'version': 2,
  'members': [
    {'postId': 'p', 'contentType': 'video', 'title': '作品'},
  ],
  'visibleCount': 1,
  'nextCursor': 'next',
  'canManage': true,
};
RemotePostCollection _remote(_Executor e) => RemotePostCollection(
  client: GeneratedCloudOperationClient(e),
  queries: GeneratedPostCollectionGraphQLClient(e),
  context: (page, key) => CloudOperationInvocationContext(
    surfaceId: 'postCollection',
    clientPageId: page,
    actor: const CloudOperationActorContext(
      accountId: 'account',
      personaId: 'owner',
    ),
    idempotencyKey: key,
  ),
);
void main() {
  test('正式registry hash与Remote变量一致，读取不走已退役GET', () async {
    final e = _Executor()
      ..response = {
        'data': {'postCollection': _page()},
      };
    final remote = _remote(e);
    final result = await remote.get(
      GetPostCollectionQuery(collectionId: 'c', limit: 7, cursor: 'opaque'),
    );
    expect(result.nextCursor, 'next');
    expect(e.operation?.method, 'POST');
    expect(e.operation?.pathTemplate, '/graphql');
    expect(e.invocation?.actor.personaId, 'owner');
    final registry = jsonDecode(
      File(
        '../quwoquan_service/services/api-edge/resources/policies/graphql_read/persisted_query_registry.example.json',
      ).readAsStringSync(),
    ) as Map;
    final entry = (registry['entries'] as List).cast<Map>().singleWhere(
      (x) => x['operationName'] == 'PostCollection',
    );
    final body = e.payload!.body as Map;
    expect(body['operationName'], 'PostCollection');
    expect(body['variables'], {
      'collectionId': 'c',
      'first': 7,
      'after': 'opaque',
    });
    expect(
      ((body['extensions'] as Map)['persistedQuery'] as Map)['sha256Hash'],
      entry['sha256Hash'],
    );
    expect(body.containsKey('query'), false);
    e.response = {
      'data': {
        'postCollectionManagement': {
          'collectionId': 'c',
          'name': '合集',
          'coverAssetId': null,
          'visibility': 'private',
          'version': 2,
          'members': [
            {'postId': 'hidden', 'readable': false, 'title': null},
          ],
        },
      },
    };
    final managed = await remote.management(
      GetPostCollectionManagementQuery(collectionId: 'c'),
    );
    expect(managed.members.single.title, isNull);
    expect((e.payload!.body as Map)['variables'], {
      'collectionId': 'c',
      'first': 100,
    });
  });
  test('正式Remote严格decoder拒绝缺nullable多余嵌套与错误分页结果', () async {
    final e = _Executor();
    final remote = _remote(e);
    for (final mutate in <void Function(Map<String, Object?>)>[
      (p) => p.remove('coverAssetId'),
      (p) => p['extra'] = true,
      (p) => p['version'] = '2',
      (p) => (p['members'] as List).first['private'] = 'secret',
      (p) => p['members'] = [null],
    ]) {
      final p = _page();
      mutate(p);
      e.response = {
        'data': {'postCollection': p},
      };
      await expectLater(
        remote.get(GetPostCollectionQuery(collectionId: 'c', limit: 20)),
        throwsFormatException,
      );
    }
    final failure = StateError('authority unavailable');
    e.failure = failure;
    final before = e.calls;
    await expectLater(
      remote.management(GetPostCollectionManagementQuery(collectionId: 'c')),
      throwsA(same(failure)),
    );
    expect(e.calls, before + 1);
  });
  test('Save Delete继续REST并携带版本幂等context', () async {
    final e = _Executor()
      ..response = {'collectionId': 'c', 'version': 3, 'status': 'active'};
    final remote = _remote(e);
    await remote.save(
      SavePostCollectionCommand(
        collectionId: 'c',
        expectedVersion: 2,
        name: '合集',
        visibility: PostCollectionVisibility.public,
        postIds: ['p'],
      ),
    );
    expect(e.operation?.method, 'PUT');
    expect(e.operation?.pathTemplate, '/content/collections/{collectionId}');
    expect(e.invocation?.idempotencyKey, isNotEmpty);
    e.response = {'collectionId': 'c', 'version': 4, 'status': 'deleted'};
    await remote.delete(
      DeletePostCollectionCommand(collectionId: 'c', expectedVersion: 3),
    );
    expect(e.operation?.method, 'DELETE');
  });
}
