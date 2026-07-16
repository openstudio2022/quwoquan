import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/context/actor_queue_partition.dart';

void main() {
  test('queue partition 同时隔离 environment/account/persona/device', () {
    final base = ActorQueuePartition(
      environment: 'gamma',
      accountId: 'account-a',
      personaId: 'persona-a',
      deviceId: 'device-a',
    );
    final variants = <ActorQueuePartition>[
      ActorQueuePartition(
        environment: 'beta',
        accountId: 'account-a',
        personaId: 'persona-a',
        deviceId: 'device-a',
      ),
      ActorQueuePartition(
        environment: 'gamma',
        accountId: 'account-b',
        personaId: 'persona-a',
        deviceId: 'device-a',
      ),
      ActorQueuePartition(
        environment: 'gamma',
        accountId: 'account-a',
        personaId: 'persona-b',
        deviceId: 'device-a',
      ),
      ActorQueuePartition(
        environment: 'gamma',
        accountId: 'account-a',
        personaId: 'persona-a',
        deviceId: 'device-b',
      ),
    ];

    expect(base.canPersist, isTrue);
    expect(variants.map((item) => item.key), everyElement(isNot(base.key)));
    expect(base.boxName('events'), isNot(contains('account-a')));
    expect(base.boxName('events'), isNot(contains('persona-a')));
    expect(base.acceptsEnvelope(base.key), isTrue);
    expect(base.acceptsEnvelope(variants.first.key), isFalse);
  });

  test('无 environment 或 actor 时禁止持久化', () {
    expect(ActorQueuePartition(environment: '').canPersist, isFalse);
    expect(ActorQueuePartition(environment: 'prod').canPersist, isFalse);
  });

  test('queue partition changes across account and persona', () {
    final actorA = ActorQueuePartition(
      environment: 'gamma',
      accountId: 'account-a',
      personaId: 'persona-a',
      deviceId: 'device-1',
    );
    final actorB = ActorQueuePartition(
      environment: 'gamma',
      accountId: 'account-b',
      personaId: 'persona-b',
      deviceId: 'device-1',
    );

    expect(actorA.canPersist, isTrue);
    expect(actorB.canPersist, isTrue);
    expect(actorA.key, isNot(actorB.key));
    expect(
      actorA.boxName('behavior_queue'),
      isNot(actorB.boxName('behavior_queue')),
    );
  });

  test('box name never exposes raw actor identifiers', () {
    final partition = ActorQueuePartition(
      environment: 'prod',
      accountId: 'sensitive-account',
      personaId: 'sensitive-persona',
      deviceId: 'sensitive-device',
    );
    final boxName = partition.boxName('ops_queue');

    expect(boxName, isNot(contains('sensitive-account')));
    expect(boxName, isNot(contains('sensitive-persona')));
    expect(boxName, isNot(contains('sensitive-device')));
  });

  test('flush accepts only the active actor partition envelope', () {
    final active = ActorQueuePartition(
      environment: 'prod',
      accountId: 'account-a',
      personaId: 'persona-a',
    );
    final previous = ActorQueuePartition(
      environment: 'prod',
      accountId: 'account-b',
      personaId: 'persona-b',
    );

    expect(active.acceptsEnvelope(active.key), isTrue);
    expect(active.acceptsEnvelope(previous.key), isFalse);
    expect(active.acceptsEnvelope(null), isFalse);
  });

  test('unidentified actor cannot persist an offline queue', () {
    final partition = ActorQueuePartition(environment: 'prod');

    expect(partition.canPersist, isFalse);
  });
}
