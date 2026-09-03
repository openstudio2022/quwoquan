import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
import 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_management_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final _contextProvider = Provider<CloudOperationInvocationContext>((ref) {
  return contentQueryInvocationContext(
    ref,
    surface: AppUiSurfaces.workBrowser,
    clientPageId: 'content.reserve.original.image.access.grant',
  );
});

void main() {
  test('认证 grant 的 persona 在投影未就绪时仍进入 content command actor', () {
    final pendingPersona = Completer<ActivePersonaContextViewData>();
    final container = ProviderContainer(
      overrides: [
        resolvedOwnerUserIdProvider.overrideWithValue('account-session'),
        resolvedActivePersonaIdProvider.overrideWithValue('persona-session'),
        activePersonaContextProvider.overrideWith((_) => pendingPersona.future),
      ],
    );
    addTearDown(container.dispose);

    final context = container.read(_contextProvider);

    expect(context.actor.accountId, 'account-session');
    expect(context.actor.personaId, 'persona-session');
  });

  test('已加载的 persona 投影优先于认证会话回退值', () async {
    final container = ProviderContainer(
      overrides: [
        resolvedOwnerUserIdProvider.overrideWithValue('account-session'),
        resolvedActivePersonaIdProvider.overrideWithValue('persona-session'),
        activePersonaContextProvider.overrideWith(
          (_) async => ActivePersonaContextViewData.fallback(
            personaId: 'persona-projected',
            ownerUserId: 'account-session',
            displayName: '投影分身',
            avatarUrl: '',
          ),
        ),
      ],
    );
    addTearDown(container.dispose);
    await container.read(activePersonaContextProvider.future);

    final context = container.read(_contextProvider);

    expect(context.actor.personaId, 'persona-projected');
  });
}
