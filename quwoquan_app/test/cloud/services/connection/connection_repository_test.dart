import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/recommendation/intersection_action_keys.dart';
import 'package:quwoquan_app/cloud/services/connection/connection_repository.dart';

void main() {
  group('MockConnectionRepository', () {
    const repo = MockConnectionRepository();

    test('getHubSummary 计数与列表长度一致', () async {
      final summary = await repo.getHubSummary();
      final affinity = await repo.listAffinityPeers();
      final nearby = await repo.listNearbyPeers();
      final trips = await repo.listCompanionTrips();
      final meetups = await repo.listOfflineMeetups();

      expect(summary.affinityCount, affinity.length);
      expect(summary.nearbyCount, nearby.length);
      expect(summary.companionCount, trips.length);
      expect(summary.meetupCount, meetups.length);
    });

    test('canonical 种子含四川目的地实体 id 与重社交 actionKey', () async {
      final trips = await repo.listCompanionTrips();
      expect(trips, isNotEmpty);
      expect(
        trips.first.destinationEntityId,
        'fixture_homepage_travel_route_daocheng',
      );
      expect(
        trips.first.actions.any(
          (a) => a.actionKey == IntersectionActionKeys.joinTrip,
        ),
        isTrue,
      );

      final nearby = await repo.listNearbyPeers();
      expect(
        nearby.any((p) => p.mutualConsentRequired && p.privacyBlurred),
        isTrue,
      );
    });
  });

  group('RemoteConnectionRepository', () {
    test('后端未上线时抛出结构化 unavailable', () async {
      const remote = RemoteConnectionRepository();
      expect(
        () => remote.getHubSummary(),
        throwsA(
          predicate(
            (Object e) => e.toString().contains('not implemented'),
          ),
        ),
      );
    });
  });
}
