import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/adapters/user_profile_cache_service.dart';

void main() {
  test('profile cache rejects version rollback, minUpdatedAt miss and source absolute expiry', () {
    var now = DateTime.utc(2026, 9, 19);
    final cache = UserProfileCacheService(
      now: () => now,
      maximumAge: const Duration(hours: 1),
    );
    cache.put('u', <String, dynamic>{
      'updatedAt': '2026-09-19T00:10:00Z',
      'displayName': 'new',
    });
    cache.put('u', <String, dynamic>{
      'updatedAt': '2026-09-19T00:05:00Z',
      'displayName': 'old',
    });
    expect(cache.get('u')?['displayName'], 'new');
    expect(
      cache.get('u', minUpdatedAt: DateTime.utc(2026, 9, 19, 0, 11)),
      isNull,
    );
    cache.put('v', <String, dynamic>{
      'updatedAt': '2026-09-19T00:00:00Z',
    }, sourceExpiresAt: now.add(const Duration(minutes: 5)));
    now = now.add(const Duration(minutes: 6));
    expect(cache.get('v'), isNull);
  });
}
