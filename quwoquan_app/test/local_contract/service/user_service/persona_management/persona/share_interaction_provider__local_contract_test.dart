// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004.t3
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-004.t4
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-005
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-007
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-007.t2
// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/owner-persona-homepage-unification/spec.md#gwt-007.t3
import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_capabilities.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/runtime/di/profile_interaction_activity_dependencies.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  // GWT-004.t1：impression 与 seen 逐条上报，打开详情才逐条 read。
  // 关键是「逐条」与「不批量」：切到 received 只是让行可见，不能顺手把整页标成已读。
  test('seen 逐条写入且切到 received 不批量标记已读', () async {
    final repository = _ShareRepository.immediate(itemCount: 3);
    final container = _container(repository);
    addTearDown(container.dispose);
    const key = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionStateProvider(key));
    await pumpEventQueue();

    final notifier = container.read(shareInteractionControllerProvider(key));
    var state = container.read(shareInteractionStateProvider(key));
    expect(state.items, hasLength(3));
    expect(repository.appendCalls, 0, reason: '进入列表本身不产生任何 read fact');
    expect(state.items.every((item) => item.readAt == null), isTrue);

    await notifier.markSeen(state.items.first.interactionId);
    state = container.read(shareInteractionStateProvider(key));
    expect(repository.appendedStates, <String>['seen']);
    expect(state.items.first.seenAt, isNotNull);
    expect(state.items.first.readAt, isNull, reason: 'seen 不等于 read');
    expect(
      state.items.skip(1).every((item) => item.seenAt == null),
      isTrue,
      reason: 'seen 只作用被上报的那一条',
    );

    await notifier.markSeen(state.items.first.interactionId);
    expect(repository.appendCalls, 1, reason: '同一条重复曝光不重复写');

    await notifier.markRead(state.items.first.interactionId);
    state = container.read(shareInteractionStateProvider(key));
    expect(repository.appendedStates, <String>['seen', 'read']);
    expect(state.items.first.readAt, isNotNull);
    expect(
      state.items.skip(1).every((item) => item.readAt == null),
      isTrue,
      reason: '打开一条详情不得把整页标成已读',
    );
  });

  // GWT-004.t2：影响文案在场才展示，服务端没给就整块不出现。
  // 这里要挡住「端侧凑一句默认文案」——那会让空归因看起来像有归因。
  test('impactPrimaryText 缺席时影响区整块不展示', () async {
    final withText = _ShareRepository.immediate(impactPrimaryText: '带来 3 次新浏览');
    final withTextContainer = _container(withText);
    addTearDown(withTextContainer.dispose);
    expect((await _received(withTextContainer)).hasImpact, isTrue);

    final blank = _ShareRepository.immediate(impactPrimaryText: '   ');
    final blankContainer = _container(blank);
    addTearDown(blankContainer.dispose);
    final item = await _received(blankContainer);
    expect(item.hasImpact, isFalse, reason: '纯空白不构成影响文案');
    expect(item.impactIsNavigable, isFalse, reason: '没有文案时更谈不上可点击');
  });

  // GWT-004.t3：文案在场与可点击是两个独立条件，缺 deepLink 只展示不跳转。
  test('影响区有文案但缺 deepLink 时不可点击', () async {
    final repository = _ShareRepository.immediate(
      impactPrimaryText: '带来 3 次新浏览',
      impactDeepLink: '',
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    final item = await _received(container);
    expect(item.hasImpact, isTrue);
    expect(
      item.impactIsNavigable,
      isFalse,
      reason: '缺 deepLink 时点击无处可去，不得渲染成可点击',
    );

    final navigable = _ShareRepository.immediate(
      impactPrimaryText: '带来 3 次新浏览',
      impactDeepLink: 'myIntersections',
    );
    final navigableContainer = _container(navigable);
    addTearDown(navigableContainer.dispose);
    expect((await _received(navigableContainer)).impactIsNavigable, isTrue);
  });

  // GWT-004.t4：未读、已读与影响数据都只属于 received；
  // initiated 侧连 read fact 都不该写出去。
  test('initiated 不显示未读已读也不显示影响数据', () async {
    final repository = _ShareRepository.immediate(
      impactPrimaryText: '带来 3 次新浏览',
      impactDeepLink: 'myIntersections',
    );
    final container = _container(repository);
    addTearDown(container.dispose);
    const initiatedKey = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.initiated,
    );
    container.read(shareInteractionStateProvider(initiatedKey));
    await pumpEventQueue();

    final initiated = container
        .read(shareInteractionStateProvider(initiatedKey))
        .items
        .single;
    expect(initiated.isUnread, isFalse);
    expect(initiated.hasImpact, isFalse, reason: '即便服务端回了文案，方向也否决展示');
    expect(initiated.impactIsNavigable, isFalse);

    await container
        .read(shareInteractionControllerProvider(initiatedKey))
        .markRead(initiated.interactionId);
    expect(
      repository.appendCalls,
      0,
      reason: 'initiated 没有已读语义，不得写 read fact',
    );

    expect((await _received(container)).isUnread, isTrue);
  });

  // GWT-007.t1：他人主页不展示 share 筛选，也不发请求。
  // 前者是 UI 可见性，后者是网络行为；只测其一时另一个可以静默漂移。
  test('他人主页既不展示 share 筛选也不发起请求', () async {
    final shares = UserProfileUIConfig.interactionSubTabs.singleWhere(
      (tab) => tab.id == 'shares',
    );
    expect(shares.visibleInMode('other'), isFalse);
    expect(UserProfileUIConfig.interactionDirectionFiltersByMode['other'], <
      String
    >['received'], reason: '他人主页没有「我发起的」方向');

    final repository = _ShareRepository.immediate();
    final container = _container(repository);
    addTearDown(container.dispose);
    const foreignKey = ShareInteractionBucketKey(
      personaId: 'persona-somebody-else',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionStateProvider(foreignKey));
    await pumpEventQueue();
    expect(
      repository.listCalls,
      0,
      reason: '非当前 active persona 的桶不得发起列表请求',
    );
    expect(
      container.read(shareInteractionStateProvider(foreignKey)).items,
      isEmpty,
    );
  });

  // GWT-007.t2：越权由服务端契约返回结构化 403，不是端侧自行编造的错误。
  test('越权错误码与恢复语义来自服务端契约', () {
    final errors = File(
      '${_repositoryRoot()}/quwoquan_service/services/content-service/contracts/content/profile_interaction_activity_view/errors.yaml',
    ).readAsStringSync();
    expect(errors, contains('code: CONTENT.USER.interaction_owner_forbidden'));
    expect(errors, contains('http_status: 403'));
    expect(
      errors,
      contains('dart_const: interactionOwnerForbidden'),
      reason: '端侧 mapper 与服务端错误码必须同源',
    );

    const mapped = ContentErrorCode.interactionOwnerForbidden;
    expect(mapped.code, 'CONTENT.USER.interaction_owner_forbidden');
    expect(
      mapped.httpStatus,
      403,
      reason: 'codegen 产物一旦与契约脱节，端侧就会把 403 映射成别的语义',
    );
    expect(mapped.recoveryAction, 'surface');
  });

  // GWT-007.t3 后半：拉黑与匿名身份的判定权在服务端投影，端侧只渲染回传字段。
  test('端侧不自行判定拉黑或匿名身份', () {
    final root = _repositoryRoot();
    final provider = File(
      '$root/quwoquan_app/lib/service/content_service/content/profile_interaction_activity_view/application/share_interaction_provider.dart',
    ).readAsStringSync();
    final models = File(
      '$root/quwoquan_app/lib/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart',
    ).readAsStringSync();
    for (final forbidden in <String>[
      'isBlocked',
      'blockedBy',
      'blockList',
      'isAnonymous',
      'anonymize',
    ]) {
      expect(
        provider,
        isNot(contains(forbidden)),
        reason: '$forbidden 属于服务端投影结论，端侧重算即出现第二套判定',
      );
      expect(models, isNot(contains(forbidden)));
    }
  });

  // GWT-007.t3 前半
  test('received/initiated 双桶独立缓存并在分身切换时清空', () async {
    final repository = _ShareRepository.immediate();
    final container = _container(repository);
    addTearDown(container.dispose);

    const receivedKey = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    const initiatedKey = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.initiated,
    );
    container.read(shareInteractionStateProvider(receivedKey));
    container.read(shareInteractionStateProvider(initiatedKey));
    await pumpEventQueue();

    expect(
      container
          .read(shareInteractionStateProvider(receivedKey))
          .items
          .single
          .direction,
      ShareInteractionDirection.received,
    );
    expect(
      container
          .read(shareInteractionStateProvider(initiatedKey))
          .items
          .single
          .direction,
      ShareInteractionDirection.initiated,
    );
    container
        .read(shareInteractionControllerProvider(receivedKey))
        .saveScrollOffset(280);
    container
        .read(shareInteractionControllerProvider(initiatedKey))
        .saveScrollOffset(640);
    expect(
      container.read(shareInteractionStateProvider(receivedKey)).scrollOffset,
      280,
    );
    expect(
      container.read(shareInteractionStateProvider(initiatedKey)).scrollOffset,
      640,
    );

    (container.read(authSessionControllerProvider.notifier)
            as _TestAuthController)
        .activate('persona-b');
    await pumpEventQueue();
    expect(
      container.read(shareInteractionStateProvider(receivedKey)).items,
      isEmpty,
    );
    expect(
      container.read(shareInteractionStateProvider(initiatedKey)).items,
      isEmpty,
    );
  });

  test('旧 generation 完成后不能覆盖新刷新结果', () async {
    final repository = _ShareRepository.deferred();
    final container = _container(repository);
    addTearDown(container.dispose);
    const key = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionStateProvider(key));
    await pumpEventQueue();
    expect(repository.pending, hasLength(1));

    final refresh = container
        .read(shareInteractionControllerProvider(key))
        .refresh();
    await pumpEventQueue();
    expect(repository.pending, hasLength(2));
    repository.pending[1].complete(_page('new-result', 'received'));
    await refresh;
    repository.pending[0].complete(_page('old-result', 'received'));
    await pumpEventQueue();

    expect(
      container
          .read(shareInteractionStateProvider(key))
          .items
          .single
          .interactionId,
      'new-result',
    );
  });

  test('read fact 失败回滚乐观态且可重试', () async {
    final repository = _ShareRepository.immediate()..failWrites = true;
    final telemetry = _CapturingTelemetryRecorder();
    final container = ProviderContainer(
      overrides: [
        profileInteractionQueryFacetProvider.overrideWithValue(repository),
        profileInteractionReadFactAppendFacetProvider.overrideWithValue(
          repository,
        ),
        authSessionControllerProvider.overrideWith(_TestAuthController.new),
        journeyEventTrackerProvider.overrideWithValue(
          JourneyEventTracker(telemetryReporter: telemetry),
        ),
      ],
    );
    addTearDown(container.dispose);
    const key = ShareInteractionBucketKey(
      personaId: 'persona-a',
      direction: ShareInteractionDirection.received,
    );
    container.read(shareInteractionStateProvider(key));
    await pumpEventQueue();
    final notifier = container.read(shareInteractionControllerProvider(key));
    final interactionId = container
        .read(shareInteractionStateProvider(key))
        .items
        .single
        .interactionId;

    await notifier.markRead(interactionId);
    var state = container.read(shareInteractionStateProvider(key));
    expect(state.items.single.readAt, isNull);
    expect(state.error, isA<StateError>());

    repository.failWrites = false;
    await notifier.markRead(interactionId);
    state = container.read(shareInteractionStateProvider(key));
    expect(state.items.single.readAt, isNotNull);
    expect(repository.appendCalls, 2);
    expect(
      telemetry.payloads.map((payload) => payload.extensions['action']),
      <Object?>['mark_read', 'mark_read'],
    );
    expect(
      telemetry.payloads.map((payload) => payload.extensions['result']),
      <Object?>['failure', 'success'],
    );
  });
}

ProviderContainer _container(_ShareRepository repository) {
  return ProviderContainer(
    overrides: [
      profileInteractionQueryFacetProvider.overrideWithValue(repository),
      profileInteractionReadFactAppendFacetProvider.overrideWithValue(
        repository,
      ),
      authSessionControllerProvider.overrideWith(_TestAuthController.new),
    ],
  );
}

String _repositoryRoot() {
  final cwd = Directory.current;
  return cwd.path.endsWith('quwoquan_app') ? cwd.parent.path : cwd.path;
}

Future<ShareInteractionItem> _received(ProviderContainer container) async {
  const key = ShareInteractionBucketKey(
    personaId: 'persona-a',
    direction: ShareInteractionDirection.received,
  );
  container.read(shareInteractionStateProvider(key));
  await pumpEventQueue();
  return container.read(shareInteractionStateProvider(key)).items.single;
}

class _TestAuthController extends AuthSessionController {
  @override
  AuthSessionState build() => const AuthSessionState(
    status: AuthSessionStatus.authenticated,
    accessToken: 'test-token',
    ownerId: 'owner-a',
    activePersonaId: 'persona-a',
  );

  void activate(String personaId) {
    state = state.copyWith(activePersonaId: personaId);
  }
}

class _ShareRepository
    implements
        ContentProfileInteractionQueryFacet,
        ContentProfileInteractionReadFactAppendFacet {
  _ShareRepository._(
    this._deferred,
    this._itemCount,
    this._impactPrimaryText,
    this._impactDeepLink,
  );

  factory _ShareRepository.immediate({
    int itemCount = 1,
    String impactPrimaryText = '带来 3 次新浏览',
    String impactDeepLink = 'myIntersections',
  }) => _ShareRepository._(
    false,
    itemCount,
    impactPrimaryText,
    impactDeepLink,
  );
  factory _ShareRepository.deferred() =>
      _ShareRepository._(true, 1, '带来 3 次新浏览', 'myIntersections');

  final bool _deferred;
  final int _itemCount;
  final String _impactPrimaryText;
  final String _impactDeepLink;
  bool failWrites = false;
  int appendCalls = 0;
  int listCalls = 0;
  final List<String> appendedStates = <String>[];
  final List<Completer<ProfileInteractionActivityPageSlice>> pending =
      <Completer<ProfileInteractionActivityPageSlice>>[];

  @override
  Future<ProfileInteractionActivityPageSlice> listActivities(
    ContentProfileInteractionPageQuery query, {
    required InteractionDirection direction,
  }) {
    listCalls += 1;
    if (!_deferred) {
      return Future.value(
        _page(
          'share-${direction.wireName}',
          direction.wireName,
          itemCount: _itemCount,
          impactPrimaryText: _impactPrimaryText,
          impactDeepLink: _impactDeepLink,
        ),
      );
    }
    final completer = Completer<ProfileInteractionActivityPageSlice>();
    pending.add(completer);
    return completer.future;
  }

  @override
  Future<ProfileInteractionReadFactAck> appendReadFact(
    AppendContentProfileInteractionReadFactCommand command,
  ) async {
    appendCalls += 1;
    if (failWrites) {
      throw StateError('read fact unavailable');
    }
    appendedStates.add(command.state.wireName);
    return ProfileInteractionReadFactAck(
      factId: 'fact-${command.activityId}-${command.state.wireName}',
      activityId: command.activityId,
      state: command.state,
      occurredAt: DateTime.utc(2026, 7, 12),
      replayed: false,
    );
  }
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  void onNetworkAvailable() {}

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }
}

ProfileInteractionActivityPageSlice _page(
  String id,
  String direction, {
  int itemCount = 1,
  String impactPrimaryText = '带来 3 次新浏览',
  String impactDeepLink = 'myIntersections',
}) {
  return ProfileInteractionActivityPageSlice(
    items: List<ProfileInteractionActivityView>.generate(
      itemCount,
      (index) => ProfileInteractionActivityView(
        ownerPersonaId: 'persona-a',
        activityId: itemCount == 1 ? id : '$id-$index',
        activityType: InteractionActivityType.share,
        direction: InteractionDirection.fromWire(
          direction,
          'ProfileInteractionActivityView.direction',
        ),
        sourceType: 'local_contract',
        sourceEventId: 'event-$id-$index',
        sourceVersion: 1,
        viewerReactionVersion: 1,
        targetVersion: 1,
        active: true,
        commentKind: 'none',
        viewerReaction: CommentReactionType.none,
        actorPersonaId: 'actor',
        actorDisplayName: '山海来信',
        actorAvatarVersion: 1,
        targetPersonaId: 'persona-a',
        targetContentId: 'target',
        targetContentType: ContentType.image,
        targetContentSummary: '川西晨光',
        targetKind: 'post',
        targetAvailability: 'active',
        targetReplyCount: 0,
        displayPersonaId: 'actor',
        displayName: '山海来信',
        displayAvatarVersion: 1,
        primaryText: '转发互动',
        previewMediaKind: 'text',
        previewText: '川西晨光',
        previewUnavailable: false,
        // 影响文案与 deepLink 只在 received 由服务端返回；initiated 侧留空，
        // 让「方向决定是否有影响数据」这条判据在 fixture 层面就能被证伪。
        // 两个方向都照原样带上服务端字段，方向过滤交给端侧判定去做——
        // 若在 fixture 里先替 initiated 抹成空，方向否决那条判据就永远测不到。
        impactPrimaryText: impactPrimaryText,
        impactDeepLink: impactDeepLink,
        filterKeys: const <String>['shares'],
        createdAt: DateTime.utc(2026, 7, 12),
        occurredAt: DateTime.utc(2026, 7, 12),
      ),
    ),
    hasMore: false,
  );
}
