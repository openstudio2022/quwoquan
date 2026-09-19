// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-008

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/assistant/scripted_assistant.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/executor/rehearsal_cloud_operation_executor.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_identity.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/content_handlers.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/handlers/handler_registry.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_store.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/transport/graphql_read/generated/search_page.g.dart';
import 'package:quwoquan_cloud_contracts/generated/gateway_contracts.dart';
import 'package:quwoquan_cloud_contracts/generated/values/user/account/account_session.values.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../support/runtime/config/runtime_package_test_hydration.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  installCanonicalOfflineAssetsForTests();

  late AlphaRehearsalStore store;
  late AlphaRehearsalCloudOperationExecutor executor;

  setUp(() {
    store = AlphaRehearsalStore(persistence: MemoryRehearsalPersistence());
    executor = AlphaRehearsalCloudOperationExecutor(
      store: store,
      registry: AlphaRehearsalHandlerRegistry.withPostExists(bundledPostExists),
    );
  });

  Future<AuthSessionGrant> login(String phone) async {
    await executor.send<OtpChallengeIssueResult>(
      appCloudOperationContracts['user.authentication_challenge.SendOtp']!,
      context: const CloudOperationInvocationContext(
        surfaceId: 'login',
        clientPageId: 'login',
        actor: CloudOperationActorContext(),
      ),
      requestEncoder: () =>
          CloudOperationRequestPayload(body: {'phone': phone}),
      responseDecoder: (wire) =>
          OtpChallengeIssueResult.fromWire(wire! as Map<String, Object?>),
    );
    return executor.send<AuthSessionGrant>(
      appCloudOperationContracts['user.account_session.LoginWithPhone']!,
      context: const CloudOperationInvocationContext(
        surfaceId: 'login',
        clientPageId: 'login',
        actor: CloudOperationActorContext(),
      ),
      requestEncoder: () => CloudOperationRequestPayload(
        body: <String, Object?>{'phone': phone, 'otpCode': rehearsalOtpCode},
      ),
      responseDecoder: (wire) =>
          AuthSessionGrant.fromWire(wire! as Map<String, Object?>),
    );
  }

  CloudOperationInvocationContext actorOf(AuthSessionGrant grant) {
    return CloudOperationInvocationContext(
      surfaceId: 'rehearsal',
      clientPageId: 'rehearsal',
      actor: CloudOperationActorContext(
        accountId: grant.ownerId,
        personaId: grant.activePersona?.personaId ?? grant.ownerId,
      ),
    );
  }

  test('synthetic 身份经单一 owner 可执行关注并取关读回', () async {
    final privateStore = AlphaRehearsalStore(
      persistence: MemoryRehearsalPersistence(),
    );
    final identityOwner = AlphaRehearsalIdentityOwner(privateStore);
    final session = SyntheticSessionResult(
      accountId: 'alpha-account:${List.filled(32, 'a').join()}',
      personaId: 'alpha-persona:${List.filled(32, 'b').join()}',
    );
    identityOwner.recordSyntheticSession('alpha-synthetic:test', session);
    await privateStore.commit(() {});
    final scopedExecutor = AlphaRehearsalCloudOperationExecutor(
      store: privateStore,
      identityOwner: identityOwner,
    );
    final context = CloudOperationInvocationContext(
      surfaceId: 'userProfile',
      clientPageId: 'userProfile',
      actor: CloudOperationActorContext(
        accountId: session.accountId,
        personaId: session.personaId,
      ),
    );
    const target = 'creator_alpha';
    Future<FollowCommandResult> setFollow(bool desired) => scopedExecutor.send(
      appCloudOperationContracts[desired
          ? 'user.persona_relationship.FollowUser'
          : 'user.persona_relationship.UnfollowUser']!,
      context: context,
      requestEncoder: () => const CloudOperationRequestPayload(
        pathParameters: {'targetPersonaId': target},
      ),
      responseDecoder: (wire) =>
          FollowCommandResult.fromWire(wire! as Map<String, Object?>),
    );

    expect((await setFollow(true)).relationState, RelationshipState.following);
    expect(privateStore.followingOf(session.personaId), contains(target));
    expect(
      (await setFollow(false)).relationState,
      RelationshipState.notFollowing,
    );
    expect(
      privateStore.followingOf(session.personaId),
      isNot(contains(target)),
    );
  });

  test(
    'generated client 在 persona context 暂未就绪时仍以 canonical persona 关注并读回',
    () async {
      final privateStore = AlphaRehearsalStore(
        persistence: MemoryRehearsalPersistence(),
      );
      final identityOwner = AlphaRehearsalIdentityOwner(privateStore);
      const accountId = 'alpha-account:cccccccccccccccccccccccccccccccc';
      const personaId = 'alpha-persona:dddddddddddddddddddddddddddddddd';
      identityOwner.recordSyntheticSession(
        'alpha-synthetic:journey',
        SyntheticSessionResult(accountId: accountId, personaId: personaId),
      );
      await privateStore.commit(() {});
      final client = GeneratedCloudOperationClient(
        AlphaRehearsalCloudOperationExecutor(
          store: privateStore,
          identityOwner: identityOwner,
        ),
      );
      const target = 'creator_alpha';
      const context = CloudOperationInvocationContext(
        surfaceId: 'homeFeed',
        clientPageId: 'followUser',
        actor: CloudOperationActorContext(accountId: accountId),
      );

      await client.userPersonaRelationshipFollowUser(
        FollowUserCommand(targetPersonaId: target, source: 'homeFeed', mutationBasis: 'test-basis', expectedVersion: 0),
        context: context,
      );
      final capability = await client
          .userPersonaRelationshipGetRelationshipCapability(
            GetRelationshipCapabilityQuery(targetPersonaId: target),
            context: context,
          );

      expect(capability.viewerPersonaId, personaId);
      expect(capability.targetPersonaId, target);
      expect(capability.relationState, RelationshipState.following);
      expect(privateStore.followingOf(personaId), contains(target));
      expect(privateStore.followingOf(accountId), isEmpty);
    },
  );

  for (final kind in SubjectFollowTargetKind.values) {
    test('Subject ${kind.wireName} 经真实 registry 关注、隔离读回及取关', () async {
      final grant = await login('00000000008');
      final other = await login('00000000009');
      final context = actorOf(grant);
      final client = GeneratedCloudOperationClient(executor);
      const subjectId = 'subject-alpha';
      final query = ListFollowingSubjectsQuery(
        subjectType: FollowSubjectKind.fromWire(kind.wireName, 'subjectType'),
      );
      final command = FollowSubjectCommand(
        subjectType: kind,
        subjectId: subjectId,
        source: 'alphaRehearsal',
      );
      await expectLater(
        client.userSubjectFollowFollowSubject(
          command,
          context: const CloudOperationInvocationContext(
            surfaceId: 'rehearsal',
            clientPageId: 'rehearsal',
            actor: CloudOperationActorContext(),
          ),
        ),
        throwsA(
          isA<CloudException>().having(
            (error) => error.code,
            'code',
            'USER.USER.unauthorized',
          ),
        ),
      );
      final followed = await client.userSubjectFollowFollowSubject(
        command,
        context: context,
      );
      expect(followed.personaId, grant.activePersona!.personaId);
      expect(followed.subjectType, kind);
      expect(followed.subjectId, subjectId);
      expect(followed.state, SubjectFollowState.following);
      expect(followed.idempotentReplay, isFalse);
      expect(
        (await client.userSubjectFollowFollowSubject(
          command,
          context: context,
        )).idempotentReplay,
        isTrue,
      );
      final page = await client.userFollowingSubjectListFollowingSubjects(
        query,
        context: context,
      );
      expect(page.items, hasLength(1));
      expect(page.items.single.subjectId, subjectId);
      expect(page.items.single.subjectType, query.subjectType);
      expect(page.items.single.targetObjectId, subjectId);
      final otherKind = SubjectFollowTargetKind.values.firstWhere(
        (candidate) => candidate != kind,
      );
      expect(
        (await client.userFollowingSubjectListFollowingSubjects(
          ListFollowingSubjectsQuery(
            subjectType: FollowSubjectKind.fromWire(
              otherKind.wireName,
              'subjectType',
            ),
          ),
          context: context,
        )).items,
        isEmpty,
      );
      expect(
        (await client.userFollowingSubjectListFollowingSubjects(
          query,
          context: actorOf(other),
        )).items,
        isEmpty,
      );

      // 重新构造 executor/store 后仍经真实 registry 读取持久事实。
      final restoredClient = GeneratedCloudOperationClient(
        AlphaRehearsalCloudOperationExecutor(
          store: AlphaRehearsalStore(persistence: store.persistence),
        ),
      );
      expect(
        (await restoredClient.userFollowingSubjectListFollowingSubjects(
          query,
          context: context,
        )).items.single.subjectId,
        subjectId,
      );
      final unfollow = UnfollowSubjectCommand(
        subjectType: kind,
        subjectId: subjectId,
      );
      final removed = await restoredClient.userSubjectFollowUnfollowSubject(
        unfollow,
        context: context,
      );
      expect(removed.state, SubjectFollowState.unfollowed);
      expect(removed.idempotentReplay, isFalse);
      expect(
        (await restoredClient.userFollowingSubjectListFollowingSubjects(
          query,
          context: context,
        )).items,
        isEmpty,
      );
      expect(
        (await restoredClient.userSubjectFollowUnfollowSubject(
          unfollow,
          context: context,
        )).idempotentReplay,
        isTrue,
      );
    });
  }

  test('关注、点赞、评论可写后读回', () async {
    final grant = await login('00000000001');
    final context = actorOf(grant);
    final target = 'creator_alpha';

    final follow = await executor.send<FollowCommandResult>(
      appCloudOperationContracts['user.persona_relationship.FollowUser']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{'targetPersonaId': target},
      ),
      responseDecoder: (wire) =>
          FollowCommandResult.fromWire(wire! as Map<String, Object?>),
    );
    expect(follow.relationState, RelationshipState.following);

    final following = await executor.send<FollowingRelationshipPageSlice>(
      appCloudOperationContracts['user.persona_relationship.ListFollowing']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{
          'personaId': grant.activePersona?.personaId ?? grant.ownerId,
        },
      ),
      responseDecoder: (wire) => FollowingRelationshipPageSlice.fromWire(
        wire! as Map<String, Object?>,
      ),
    );
    expect(following.items.map((item) => item.personaId), contains(target));

    final bundlePost =
        (await OfflineContentBundle.load()).rows('posts').first['detail']!
            as Map;
    final postId = bundlePost['postId']! as String;
    final liked = await executor.send<ContentReactionCommandResult>(
      appCloudOperationContracts['content.content_reaction.LikePost']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{'postId': postId},
      ),
      responseDecoder: (wire) =>
          ContentReactionCommandResult.fromWire(wire! as Map<String, Object?>),
    );
    expect(liked.liked, isTrue);
    expect(liked.changed, isTrue);

    final state = await executor.send<ContentReactionStateSlice>(
      appCloudOperationContracts['content.content_reaction.GetContentReactionState']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{'postId': postId},
      ),
      responseDecoder: (wire) =>
          ContentReactionStateSlice.fromWire(wire! as Map<String, Object?>),
    );
    expect(state.liked, isTrue);

    final created = await executor.send<CommentCommandResult>(
      appCloudOperationContracts['content.comment.CreateComment']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{'postId': postId},
        body: const <String, Object?>{'content': '本地评论'},
      ),
      responseDecoder: (wire) =>
          CommentCommandResult.fromWire(wire! as Map<String, Object?>),
    );
    expect(created.status, CommentStatus.active);

    final comments = await executor.send<CommentPageSlice>(
      appCloudOperationContracts['content.comment.ListComments']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{'postId': postId},
      ),
      responseDecoder: (wire) =>
          CommentPageSlice.fromWire(wire! as Map<String, Object?>),
    );
    expect(comments.items.map((item) => item.content), contains('本地评论'));
  });

  test('两个演练身份可互相收发消息', () async {
    final alice = await login('00000000002');
    final bob = await login('00000000003');
    final aliceContext = actorOf(alice);
    final bobId = bob.activePersona?.personaId ?? bob.ownerId;

    final conversation = await executor.send<ChatConversation>(
      appCloudOperationContracts['chat.conversation.CreateConversation']!,
      context: aliceContext,
      requestEncoder: () => CloudOperationRequestPayload(
        body: <String, Object?>{
          'type': 'direct',
          'initialMemberIds': <Object>[bobId],
        },
      ),
      responseDecoder: (wire) =>
          ChatConversation.fromWire(wire! as Map<String, Object?>),
    );

    final sent = await executor.send<ChatSendMessageResult>(
      appCloudOperationContracts['chat.message.SendMessage']!,
      context: aliceContext,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{
          'conversationId': conversation.conversationId,
        },
        body: <String, Object?>{'type': 'text', 'content': '你好'},
      ),
      responseDecoder: (wire) =>
          ChatSendMessageResult.fromWire(wire! as Map<String, Object?>),
    );
    expect(sent.seq, 1);

    final bobContext = actorOf(bob);
    final messages = await executor.send<MessagePageSlice>(
      appCloudOperationContracts['chat.message.ListMessages']!,
      context: bobContext,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{
          'conversationId': conversation.conversationId,
        },
      ),
      responseDecoder: (wire) =>
          MessagePageSlice.fromWire(wire! as Map<String, Object?>),
    );
    expect(messages.items.map((item) => item.content), contains('你好'));
  });

  test('搜索走签名 GraphQL 投影并按 actor 绑定分页游标', () async {
    final grant = await login('00000000004');
    final context = actorOf(grant);
    final client = GeneratedSearchPageGraphQLClient(executor);

    final first = await client.searchPage(
      SearchPageInput(
        query: '三峡',
        first: 1,
        objectTypes: const <String>['CONTENT_POST'],
      ),
      context: context,
    );
    expect(first.searchRequestId, isNotEmpty);
    expect(first.items, hasLength(1));
    expect(first.items.single.resultType, SearchPageObjectType.contentPost);
    expect(first.items.single.title, contains('三峡'));
    expect(first.items.single.action, startsWith('quwoquan://content/post/'));
    expect(first.nextCursor, isNotNull);

    final second = await client.searchPage(
      SearchPageInput(
        query: '三峡',
        first: 1,
        after: first.nextCursor,
        objectTypes: const <String>['CONTENT_POST'],
      ),
      context: context,
    );
    expect(second.items, hasLength(1));
    expect(second.items.single.objectRef, isNot(first.items.single.objectRef));

    final other = actorOf(await login('00000000006'));
    await expectLater(
      client.searchPage(
        SearchPageInput(
          query: '三峡',
          first: 1,
          after: first.nextCursor,
          objectTypes: const <String>['CONTENT_POST'],
        ),
        context: other,
      ),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          'GATEWAY.USER.graphql_request_invalid',
        ),
      ),
    );
  });

  test('搜索空命中合法，坏输入 typed fail', () async {
    final context = actorOf(await login('00000000007'));
    final client = GeneratedSearchPageGraphQLClient(executor);

    final empty = await client.searchPage(
      SearchPageInput(query: '不存在的演练关键词'),
      context: context,
    );
    expect(empty.items, isEmpty);
    expect(empty.nextCursor, isNull);
    expect(empty.searchRequestId, isNotEmpty);

    await expectLater(
      client.searchPage(SearchPageInput(query: '   '), context: context),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'code',
          'GATEWAY.USER.graphql_request_invalid',
        ),
      ),
    );
    await expectLater(
      client.searchPage(
        SearchPageInput(query: '三峡', first: 21),
        context: context,
      ),
      throwsA(isA<CloudException>()),
    );
  });

  test('小趣流标注模拟并可取消', () async {
    final grant = await login('00000000005');
    final context = actorOf(grant);
    final session = await executor.send<AssistantSessionWire>(
      appCloudOperationContracts['assistant.assistant_session.CreateAssistantSession']!,
      context: context,
      requestEncoder: () => const CloudOperationRequestPayload(),
      responseDecoder: decodeAssistantSessionWire,
    );
    expect(session.summary, contains(rehearsalAssistantMarker));

    final run = await executor.send<AssistantRunEnvelopeWire>(
      appCloudOperationContracts['assistant.assistant_run.StartAssistantRun']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{'sessionId': session.sessionId},
        body: <String, Object?>{'sessionId': session.sessionId},
      ),
      responseDecoder: decodeAssistantRunEnvelopeWire,
    );

    final stream = executor.stream<AssistantStreamEventWire>(
      appCloudOperationContracts['assistant.assistant_run.StreamAssistantRunEvents']!,
      context: context,
      requestEncoder: () => CloudOperationRequestPayload(
        pathParameters: <String, String>{
          'sessionId': session.sessionId,
          'runId': run.runId,
        },
      ),
      responseDecoder: decodeAssistantStreamEventWire,
    );
    final events = <AssistantStreamEventWire>[];
    await for (final event in stream) {
      events.add(event);
      if (event.eventType == AssistantStreamEventType.answerDelta) {
        await executor.send<AssistantRunEnvelopeWire>(
          appCloudOperationContracts['assistant.assistant_run.CancelAssistantRun']!,
          context: context,
          requestEncoder: () => CloudOperationRequestPayload(
            pathParameters: {'runId': run.runId},
          ),
          responseDecoder: decodeAssistantRunEnvelopeWire,
        );
      }
    }
    expect(
      events.map((e) => e.eventType),
      isNot(contains(AssistantStreamEventType.completed)),
    );
    expect(store.assistantRuns[run.runId]!['status'], 'cancelled');
    final other = actorOf(await login('00000000006'));
    await expectLater(
      executor
          .stream<AssistantStreamEventWire>(
            appCloudOperationContracts['assistant.assistant_run.StreamAssistantRunEvents']!,
            context: other,
            requestEncoder: () => CloudOperationRequestPayload(
              pathParameters: {
                'runId': run.runId,
                'sessionId': session.sessionId,
              },
            ),
            responseDecoder: decodeAssistantStreamEventWire,
          )
          .toList(),
      throwsA(isA<Object>()),
    );
    expect(events, isNotEmpty);
    expect(
      events.map((event) => event.eventType),
      contains(AssistantStreamEventType.answerDelta),
    );
    expect(
      events.any(
        (event) =>
            '${event.payload['text'] ?? ''}'.contains(rehearsalAssistantMarker),
      ),
      isTrue,
    );
    expect(rehearsalAssistantScriptVersion, startsWith('rehearsal.xiaoqu.'));
  });
}
