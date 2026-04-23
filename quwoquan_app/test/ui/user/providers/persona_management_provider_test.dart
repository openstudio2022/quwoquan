import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/cloud/services/user/user_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/user/providers/persona_management_provider.dart';

class _FakeAnalyticsService extends AnalyticsService {
  _FakeAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

void main() {
  group('PersonaManagementNotifier telemetry', () {
    test('create / activate / retire / quota reached 记录成功事件', () async {
      final analytics = _FakeAnalyticsService();
      final container = ProviderContainer(
        overrides: [
          userRepositoryProvider.overrideWithValue(MockUserRepository()),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(personaManagementProvider.notifier);

      await notifier.createPersona(displayName: '摄影分身', userHandle: 'photo');
      await notifier.activatePersona('persona_1');
      await notifier.retirePersona('persona_2');
      await notifier.trackQuotaReached(5);

      expect(
        analytics.events.map((event) => event.eventName),
        containsAll(<String>[
          'create_succeeded',
          'activate_succeeded',
          'retired_count',
          'retire_succeeded',
          'quota_reached',
        ]),
      );
    });
  });
}
