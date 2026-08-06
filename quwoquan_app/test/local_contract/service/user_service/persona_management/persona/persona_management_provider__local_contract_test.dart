// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/persona_management_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../../../../support/service/user_service/persona_management/persona/test_persona_facets.dart';

class _FakeAnalyticsService extends AnalyticsService {
  _FakeAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // activatePersona 现在会同步更新 AuthSession 的 activePersona，
    // 该链路依赖 SharedPreferences，需在测试态提供 mock 存储。
    SharedPreferences.setMockInitialValues(<String, Object>{});
  });

  group('PersonaManagementNotifier telemetry', () {
    test('create / activate / retire / quota reached 记录成功事件', () async {
      final analytics = _FakeAnalyticsService();
      final persona = TestPersonaFacets();
      final container = ProviderContainer(
        overrides: [
          personaQueryProvider.overrideWith((ref, surface) => persona),
          personaCommandWriterProvider.overrideWithValue(persona),
          analyticsProvider.overrideWithValue(analytics),
        ],
      );
      addTearDown(container.dispose);

      final notifier = container.read(personaManagementProvider.notifier);

      final created = await notifier.createPersona(displayName: '测试新分身');
      expect(created, isNotNull);
      await notifier.activatePersona('persona_photo');
      await notifier.activatePersona('persona_primary');
      await notifier.retirePersona('persona_photo');
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
