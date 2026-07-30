// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-suspension-and-appeal-lifecycle/spec.md#gwt-004

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/auth/account_restriction_support.dart';
import 'package:quwoquan_app/core/di/login_dependencies.dart';

void main() {
  test('支持入口只接受环境注入的 HTTPS 官网根，不合成 appeal path 或 case', () async {
    Uri? opened;
    final launcher = PublicWebAccountRestrictionSupportLauncher(
      publicWebBaseUrl: 'https://www.example.com/public',
      opener: (uri) async {
        opened = uri;
        return true;
      },
    );

    expect(await launcher.openOfficialSupport(), isTrue);
    expect(opened, Uri.parse('https://www.example.com/public'));
    expect(opened?.queryParameters, isEmpty);
    expect(opened.toString(), isNot(contains('appeal')));
    expect(opened.toString(), isNot(contains('case')));

    expect(officialSupportDestination('http://www.example.com'), isNull);
    expect(
      officialSupportDestination('https://user@example.com/support'),
      isNull,
    );
    expect(
      officialSupportDestination('https://www.example.com/#case-secret'),
      isNull,
    );
  });

  test('登录组合根只暴露同一个支持 launcher Provider', () async {
    final fake = _RecordingSupportLauncher();
    final container = ProviderContainer(
      overrides: [
        accountRestrictionSupportLauncherProvider.overrideWithValue(fake),
      ],
    );
    addTearDown(container.dispose);

    expect(
      await container
          .read(accountRestrictionSupportLauncherProvider)
          .openOfficialSupport(),
      isTrue,
    );
    expect(fake.calls, 1);
  });
}

final class _RecordingSupportLauncher
    implements AccountRestrictionSupportLauncher {
  int calls = 0;

  @override
  Future<bool> openOfficialSupport() async {
    calls += 1;
    return true;
  }
}
