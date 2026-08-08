// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-002
// readiness_case: contact_discovery_record_initiate_contact_discovery_app_local
import 'dart:async';
import 'dart:collection';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_outbox.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_reporter.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/platform/contacts/device_contacts_gateway.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_discovery_remote.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_hash_service.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/presentation/phone_contacts_page.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/cloud_boundary_test_scope.dart';

const _phoneAlice = '13800138000';
const _phoneBob = '13900139000';
const _hasher = ContactHashService();

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late AppPermissionCoordinator permissionCoordinator;

  setUp(() {
    permissionCoordinator = AppPermissionCoordinator.createForTest();
    permissionCoordinator.ensureLifecycleAttached();
    permissionCoordinator.phaseReaders[AppPermissionKind.contacts] = () async =>
        AppPermissionPhase.granted;
    permissionCoordinator.grantCheckers[AppPermissionKind.contacts] =
        () async => true;
    AppPermissionCoordinator.debugInstance = permissionCoordinator;
  });

  tearDown(() {
    WidgetsBinding.instance.removeObserver(permissionCoordinator);
    AppPermissionCoordinator.debugInstance = null;
  });

  testWidgets('通讯录页真实呈现能力不可用终态且不请求系统权限', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          ...sealedCloudBoundaryOverrides(),
          platformCapabilitiesProvider.overrideWithValue(CapabilityProfile.web),
        ],
        child: const CupertinoApp(home: PhoneContactsPage()),
      ),
    );
    await tester.pump();

    expect(find.text(ContactText.addContactPhoneEntryTitle), findsOneWidget);
    expect(find.text(ContactText.phoneContactsUnavailable), findsOneWidget);
    expect(find.text(ContactText.phoneContactsPermissionCta), findsNothing);
  });

  test('同一联系人快照失败重试复用 intent，成功后新刷新换 key', () async {
    final executor = _SequencedCloudExecutor(<FutureOr<Object?> Function()>[
      () => throw StateError('connection lost after request write'),
      () => _wireResult('discovery-replayed'),
      () => _wireResult('discovery-refreshed'),
    ]);
    final client = GeneratedCloudOperationClient(executor);
    final facet = RemoteContactDiscoveryFacet(
      client: client,
      invocationContext: (clientPageId, {String? idempotencyKey}) =>
          CloudOperationInvocationContext(
            surfaceId: 'addContactPhone',
            clientPageId: clientPageId,
            idempotencyKey: idempotencyKey,
            actor: const CloudOperationActorContext(
              accountId: 'owner-current',
              personaId: 'persona-current',
            ),
          ),
    );
    final keys = Queue<String>.from(<String>['intent-1', 'intent-2']);
    final repository = RemoteContactDiscoveryRepository(
      commandWriter: facet,
      query: facet,
      idempotencyKeyFactory: keys.removeFirst,
    );
    final snapshot = <String>[
      _hasher.hash(_phoneAlice),
      _hasher.hash(_phoneBob),
    ]..sort();
    final reorderedSnapshot = <String>[
      snapshot.last,
      snapshot.first,
      snapshot.last,
    ];

    await expectLater(
      repository.initiate(snapshot),
      throwsA(isA<StateError>()),
    );
    expect(
      (await repository.initiate(reorderedSnapshot)).id,
      'discovery-replayed',
    );
    expect((await repository.initiate(snapshot)).id, 'discovery-refreshed');

    expect(executor.idempotencyKeys, <String>[
      'intent-1',
      'intent-1',
      'intent-2',
    ]);
    expect(
      executor.operationIds,
      everyElement(
        AppCloudOperationIds.userContactDiscoveryRecordInitiateContactDiscovery,
      ),
    );
    expect(
      executor.requestBodies,
      everyElement(<String, Object?>{'hashedPhones': snapshot}),
    );
  });

  testWidgets('只上传端侧哈希并以 fresh capability 和 Remote 读回确认关注', (tester) async {
    final gateway = _DeviceContactsGatewayDouble.immediate(
      <DeviceContactRecord>[
        const DeviceContactRecord(
          displayName: '本机 Alice',
          phoneNumbers: <String>[_phoneAlice],
        ),
      ],
    );
    final discovery = _DiscoveryRepositoryDouble(
      (_) => _discoveryResult(
        id: 'discovery-alice',
        phone: _phoneAlice,
        targetPersonaId: 'persona-alice',
      ),
    );
    final capabilities = _CapabilitySequence(<RelationshipCapabilityViewData>[
      _capability(),
      _capability(relationState: 'following', canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands();
    final telemetry = _CapturingTelemetryRecorder();
    await _pumpPhoneContactsPage(
      tester,
      gateway: gateway,
      discovery: discovery,
      capabilities: capabilities,
      commands: commands,
      telemetry: telemetry,
    );

    await tester.tap(find.text(ContactText.phoneContactsPermissionCta));
    await tester.pumpAndSettle();

    expect(discovery.initiated, <List<String>>[
      <String>[_hasher.hash(_phoneAlice)],
    ]);
    expect(discovery.initiated.single, isNot(contains(_phoneAlice)));
    expect(gateway.timeouts, <Duration>[const Duration(seconds: 8)]);
    expect(find.text('本机 Alice'), findsOneWidget);

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(commands.followedTargets, <String>['persona-alice']);
    expect(capabilities.calls, 2);
    _expectContactAction(
      tester,
      ContactText.contactAlreadyAdded,
      enabled: false,
    );
    expect(telemetry.payloads.join(), isNot(contains(_phoneAlice)));
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('canFollow=false 不发命令，保留候选且清 pending 后显式重试', (tester) async {
    final capabilities = _CapabilitySequence(<RelationshipCapabilityViewData>[
      _capability(canFollow: false, isBlocked: true),
      _capability(),
      _capability(relationState: 'following', canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands();
    await _pumpLoadedAlice(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(commands.followedTargets, isEmpty);
    expect(find.text('本机 Alice'), findsOneWidget);
    expect(find.text(ContentText.tryAgain), findsOneWidget);

    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();

    expect(commands.followedTargets, <String>['persona-alice']);
    _expectContactAction(
      tester,
      ContactText.contactAlreadyAdded,
      enabled: false,
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('Follow failure 保留候选且 retry 真实重发后读回', (tester) async {
    final capabilities = _CapabilitySequence(<RelationshipCapabilityViewData>[
      _capability(),
      _capability(),
      _capability(relationState: 'following', canFollow: false),
    ]);
    final commands = _RecordingRelationshipCommands(<Future<void> Function()>[
      () => throw StateError('follow failed'),
      () async {},
    ]);
    await _pumpLoadedAlice(
      tester,
      capabilities: capabilities,
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();
    expect(find.text('本机 Alice'), findsOneWidget);
    expect(find.text(ContactText.addContact), findsOneWidget);

    await tester.tap(find.text(ContentText.tryAgain));
    await tester.pumpAndSettle();
    expect(commands.followedTargets, <String>[
      'persona-alice',
      'persona-alice',
    ]);
    _expectContactAction(
      tester,
      ContactText.contactAlreadyAdded,
      enabled: false,
    );
    await tester.pump(const Duration(seconds: 4));
  });

  testWidgets('Follow ACK 后读回未收敛仍保留候选且不显示伪成功', (tester) async {
    final commands = _RecordingRelationshipCommands();
    await _pumpLoadedAlice(
      tester,
      capabilities: _CapabilitySequence(<RelationshipCapabilityViewData>[
        _capability(),
        _capability(),
      ]),
      commands: commands,
    );

    await tester.tap(find.text(ContactText.addContact));
    await tester.pumpAndSettle();

    expect(commands.followedTargets, <String>['persona-alice']);
    expect(find.text('本机 Alice'), findsOneWidget);
    expect(find.text(ContactText.addContact), findsOneWidget);
    expect(find.text(ContactText.contactAlreadyAdded), findsNothing);
  });

  testWidgets('并发通讯录读取只接受最新 generation，晚到结果不能覆盖', (tester) async {
    final first = Completer<List<DeviceContactRecord>>();
    final second = Completer<List<DeviceContactRecord>>();
    final gateway = _DeviceContactsGatewayDouble(
      <Future<List<DeviceContactRecord>> Function()>[
        () => first.future,
        () => second.future,
      ],
    );
    final discovery = _DiscoveryRepositoryDouble((hashes) {
      final isAlice = hashes.contains(_hasher.hash(_phoneAlice));
      return _discoveryResult(
        id: isAlice ? 'discovery-alice' : 'discovery-bob',
        phone: isAlice ? _phoneAlice : _phoneBob,
        targetPersonaId: isAlice ? 'persona-alice' : 'persona-bob',
      );
    });
    await _pumpPhoneContactsPage(
      tester,
      gateway: gateway,
      discovery: discovery,
      capabilities: _CapabilitySequence(
        const <RelationshipCapabilityViewData>[],
      ),
      commands: _RecordingRelationshipCommands(),
      telemetry: _CapturingTelemetryRecorder(),
    );
    final cta = tester.widget<CupertinoButton>(
      find.ancestor(
        of: find.text(ContactText.phoneContactsPermissionCta),
        matching: find.byType(CupertinoButton),
      ),
    );

    cta.onPressed!();
    await tester.pump();
    expect(gateway.calls, 1);
    cta.onPressed!();
    await tester.pump();
    expect(gateway.calls, 2);
    expect(gateway.timeouts, <Duration>[
      const Duration(seconds: 8),
      const Duration(seconds: 8),
    ]);

    second.complete(<DeviceContactRecord>[
      const DeviceContactRecord(
        displayName: '本机 Bob',
        phoneNumbers: <String>[_phoneBob],
      ),
    ]);
    await tester.pump();
    expect(discovery.initiated, hasLength(1));
    await tester.pump();
    await tester.pumpAndSettle();
    expect(find.text('本机 Bob'), findsOneWidget);

    first.complete(<DeviceContactRecord>[
      const DeviceContactRecord(
        displayName: '本机 Alice',
        phoneNumbers: <String>[_phoneAlice],
      ),
    ]);
    await tester.pumpAndSettle();
    expect(find.text('本机 Bob'), findsOneWidget);
    expect(find.text('本机 Alice'), findsNothing);
  });
}

void _expectContactAction(
  WidgetTester tester,
  String label, {
  required bool enabled,
}) {
  final matches = tester
      .widgetList<CupertinoButton>(find.byType(CupertinoButton))
      .where(
        (button) =>
            button.child is Text &&
            (button.child as Text).data == label &&
            (button.onPressed != null) == enabled,
      );
  expect(matches, hasLength(1));
}

Future<void> _pumpLoadedAlice(
  WidgetTester tester, {
  required _CapabilitySequence capabilities,
  required _RecordingRelationshipCommands commands,
}) async {
  await _pumpPhoneContactsPage(
    tester,
    gateway: _DeviceContactsGatewayDouble.immediate(<DeviceContactRecord>[
      const DeviceContactRecord(
        displayName: '本机 Alice',
        phoneNumbers: <String>[_phoneAlice],
      ),
    ]),
    discovery: _DiscoveryRepositoryDouble(
      (_) => _discoveryResult(
        id: 'discovery-alice',
        phone: _phoneAlice,
        targetPersonaId: 'persona-alice',
      ),
    ),
    capabilities: capabilities,
    commands: commands,
    telemetry: _CapturingTelemetryRecorder(),
  );
  await tester.tap(find.text(ContactText.phoneContactsPermissionCta));
  await tester.pumpAndSettle();
}

Future<void> _pumpPhoneContactsPage(
  WidgetTester tester, {
  required DeviceContactsGateway gateway,
  required ContactDiscoveryRepository discovery,
  required RelationshipCapabilityRepository capabilities,
  required PersonaRelationshipCommandWriter commands,
  required AppTelemetryRecorder telemetry,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: <Override>[
        ...sealedCloudBoundaryOverrides(),
        platformCapabilitiesProvider.overrideWithValue(
          CapabilityProfile.mobile,
        ),
        deviceContactsGatewayProvider.overrideWithValue(gateway),
        contactDiscoveryRepositoryProvider.overrideWithValue(discovery),
        relationshipCapabilityRepositoryForSurfaceProvider.overrideWith(
          (ref, surface) => capabilities,
        ),
        personaRelationshipCommandWriterProvider.overrideWith(
          (ref, surface) => commands,
        ),
        journeyEventTrackerProvider.overrideWithValue(
          JourneyEventTracker(telemetryReporter: telemetry),
        ),
      ],
      child: const CupertinoApp(home: PhoneContactsPage()),
    ),
  );
  await tester.pump();
}

Map<String, Object?> _wireResult(String id) => <String, Object?>{
  'id': id,
  'status': 'completed',
  'matchedPersonaIds': <Object?>[],
  'matchCount': 0,
  'matches': <Object?>[],
};

ContactDiscoveryResultView _discoveryResult({
  required String id,
  required String phone,
  required String targetPersonaId,
}) => ContactDiscoveryResultView(
  id: id,
  status: 'completed',
  matchedPersonaIds: <String>[targetPersonaId],
  matchCount: 1,
  matches: <ContactDiscoveryMatchView>[
    ContactDiscoveryMatchView(
      hashedPhone: _hasher.hash(phone),
      personaId: targetPersonaId,
      userHandle: targetPersonaId,
      displayName: targetPersonaId,
      avatarUrl: null,
      avatarVersion: 0,
      region: null,
      relationshipCapability: _capability(targetPersonaId: targetPersonaId),
    ),
  ],
);

RelationshipCapabilityViewData _capability({
  String targetPersonaId = 'persona-alice',
  String relationState = 'not_following',
  bool canFollow = true,
  bool isBlocked = false,
  bool isBlockedBy = false,
}) => RelationshipCapabilityViewData(
  viewerPersonaId: 'persona-viewer',
  targetPersonaId: targetPersonaId,
  relationState: relationState,
  canFollow: canFollow,
  canUnfollow: relationState == 'following' || relationState == 'mutual',
  canFollowBack: false,
  canGreet: false,
  canCreateDirectConversation: false,
  canSendMessage: false,
  canOpenConversation: false,
  hasPendingGreeting: false,
  hasFormalConversation: false,
  canStartVoiceCall: false,
  canStartVideoCall: false,
  isBlocked: isBlocked,
  isBlockedBy: isBlockedBy,
);

final class _SequencedCloudExecutor implements CloudOperationExecutor {
  _SequencedCloudExecutor(Iterable<FutureOr<Object?> Function()> plans)
    : _plans = Queue<FutureOr<Object?> Function()>.from(plans);

  final Queue<FutureOr<Object?> Function()> _plans;
  final List<String> idempotencyKeys = <String>[];
  final List<String> operationIds = <String>[];
  final List<Object?> requestBodies = <Object?>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    operationIds.add(operation.canonicalOperationId);
    idempotencyKeys.add(context.idempotencyKey ?? '');
    requestBodies.add(requestEncoder().body);
    final response = await _plans.removeFirst()();
    return responseDecoder(response);
  }
}

final class _DeviceContactsGatewayDouble implements DeviceContactsGateway {
  _DeviceContactsGatewayDouble(
    Iterable<Future<List<DeviceContactRecord>> Function()> plans,
  ) : _plans = Queue<Future<List<DeviceContactRecord>> Function()>.from(plans);

  factory _DeviceContactsGatewayDouble.immediate(
    List<DeviceContactRecord> contacts,
  ) => _DeviceContactsGatewayDouble(
    <Future<List<DeviceContactRecord>> Function()>[() async => contacts],
  );

  final Queue<Future<List<DeviceContactRecord>> Function()> _plans;
  int calls = 0;
  final List<Duration> timeouts = <Duration>[];

  @override
  bool get isSupported => true;

  @override
  Future<List<DeviceContactRecord>> readContacts({required Duration timeout}) {
    calls += 1;
    timeouts.add(timeout);
    return _plans.removeFirst()();
  }
}

final class _DiscoveryRepositoryDouble implements ContactDiscoveryRepository {
  _DiscoveryRepositoryDouble(this._resolve);

  final ContactDiscoveryResultView Function(List<String> hashes) _resolve;
  final List<List<String>> initiated = <List<String>>[];

  @override
  Future<ContactDiscoveryResultView> initiate(List<String> hashedPhones) async {
    initiated.add(List<String>.unmodifiable(hashedPhones));
    return _resolve(hashedPhones);
  }

  @override
  Future<ContactDiscoveryResultView?> getLatest() async => null;

  @override
  Future<void> dismiss(String id) async {}
}

final class _CapabilitySequence implements RelationshipCapabilityRepository {
  _CapabilitySequence(Iterable<RelationshipCapabilityViewData> values)
    : _values = Queue<RelationshipCapabilityViewData>.from(values);

  final Queue<RelationshipCapabilityViewData> _values;
  int calls = 0;

  @override
  bool get reconcilesCapabilityWithSharedRelationshipState => true;

  @override
  Future<RelationshipCapabilityViewData> getCapability(
    String targetUserId,
  ) async {
    calls += 1;
    return _values.removeFirst();
  }
}

final class _RecordingRelationshipCommands
    implements PersonaRelationshipCommandWriter {
  _RecordingRelationshipCommands([
    Iterable<Future<void> Function()> outcomes =
        const <Future<void> Function()>[],
  ]) : _outcomes = Queue<Future<void> Function()>.from(outcomes);

  final Queue<Future<void> Function()> _outcomes;
  final List<String> followedTargets = <String>[];

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) async {
    followedTargets.add(targetPersonaId);
    if (_outcomes.isNotEmpty) {
      await _outcomes.removeFirst()();
    }
  }

  @override
  Future<void> unfollow(String targetPersonaId) async {
    throw UnimplementedError();
  }
}

final class _CapturingTelemetryRecorder implements AppTelemetryRecorder {
  final List<AppTelemetryPayload> payloads = <AppTelemetryPayload>[];

  @override
  Future<AppTelemetryRecordResult> record(
    AppTelemetryPayload payload, {
    String? pageName,
    DateTime? occurredAt,
  }) async {
    payloads.add(payload);
    return AppTelemetryRecordResult.accepted;
  }

  @override
  Future<AppTelemetryFlushResult> flush() async =>
      AppTelemetryFlushResult.empty;

  @override
  Future<void> clearPendingForLogout() async {}

  @override
  void onNetworkAvailable() {}
}
