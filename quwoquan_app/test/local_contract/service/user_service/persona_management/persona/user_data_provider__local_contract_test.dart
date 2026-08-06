/// spec_ref: specs/feature-tree/user-identity-profile-relationship/profile-homepage-redesign/profile-commercial-readiness/spec.md#gwt-001
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

final class _ThrowingProfileQuery implements ProfileQuery {
  const _ThrowingProfileQuery();

  @override
  Future<Never> getUserHomepageBundle(String personaId) async {
    throw StateError('profile transport unavailable');
  }

  @override
  Future<Never> getUserProfile(String userId) async {
    throw StateError('profile transport unavailable');
  }

  @override
  Future<Never> getUserStats(String userId) async {
    throw StateError('profile transport unavailable');
  }

  @override
  Future<Never> searchSocialRelations({
    required String query,
    int limit = 20,
  }) async {
    throw StateError('profile transport unavailable');
  }
}

void main() {
  test('档案读取失败不合成用户名快照', () async {
    final container = ProviderContainer(
      overrides: [
        profileQueryProvider.overrideWith(
          (ref, surface) => const _ThrowingProfileQuery(),
        ),
      ],
    );
    addTearDown(container.dispose);

    await container
        .read(userDataProvider.notifier)
        .loadUser('profile_subject', sourceSurface: AppUiSurfaces.profileHome);

    expect(container.read(userDataProvider), isNull);
  });
}
