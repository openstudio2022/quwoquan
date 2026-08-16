import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../../../../support/service/content_service/content/content_behavior_fact/recording_content_behavior_repository.dart';
import '../../../../../support/service/chat_service/chat/conversation/chat_repository_facet_overrides.dart';
import '../../../../../support/service/recommendation_service/recommendation/recommendation_feature_profile_view/intersection_repository_typed_double.dart';
import '../../../../../support/service/entity_service/entity_homepage/homepage/homepage_test_adapter.dart';
import '../../../../../support/runtime/homepage_source_cards_boundary_overrides.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_detail_page.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart'
    show ObjectHomepageText;
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show intersectionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart'
    show homepageFacetSetProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart'
    show contentRuntimeConfigProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart'
    show buildProductionContentRuntimeConfigDefaults;
import 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart'
    show homepageIntroductionRepositoryProvider;
import 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart'
    show behaviorRepositoryProvider;
import 'package:quwoquan_app/runtime/shell/share/forward_share_sheet.dart';

/// GWT（homepage-entry-and-preview 分享分发面）：
/// - Given 已发布主页详情，When 点击顶栏分享，Then 打开统一转发面板
///   （链接/深链由 metadata link 模板 codegen 提供，无第二套 URL 真相源）。
/// - more 菜单同样提供「分享主页」入口。
void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
    originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      originalOnError?.call(details);
    };
  });

  tearDown(() {
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  Widget buildApp() {
    return ProviderScope(
      overrides: [
        ...homepageSourceCardsBoundaryOverrides(),
        authSessionControllerProvider.overrideWith(_GuestHomepageSession.new),
        behaviorRepositoryProvider.overrideWithValue(
          RecordingContentBehaviorRepository(),
        ),
        intersectionRepositoryProvider.overrideWithValue(
          InMemoryIntersectionRepository(),
        ),
        ...chatTestRepositoryOverrides(),
        contentRuntimeConfigProvider.overrideWithValue(
          buildProductionContentRuntimeConfigDefaults(),
        ),
        homepageFacetSetProvider.overrideWithValue(MockHomepageRepository()),
        homepageIntroductionRepositoryProvider.overrideWithValue(
          const MockHomepageIntroductionRepository(),
        ),
      ],
      child: const MaterialApp(
        home: HomepageDetailPage(homepageId: 'homepage_sight_west_lake'),
      ),
    );
  }

  testWidgets('已发布主页点击顶栏分享打开统一转发面板', (tester) async {
    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    final shareButton = find.byKey(
      const ValueKey<String>('object-chrome-share'),
    );
    expect(shareButton, findsOneWidget);
    await tester.tap(shareButton);
    await tester.pumpAndSettle();

    expect(find.byType(ForwardShareSheet), findsOneWidget);
    expect(find.text(ChatText.forwardMostContacted), findsOneWidget);
  });

  testWidgets('更多菜单包含分享主页动作并打开统一转发面板', (tester) async {
    await tester.pumpWidget(buildApp());
    await tester.pumpAndSettle();

    final moreButton = find.byKey(const ValueKey<String>('object-chrome-more'));
    expect(moreButton, findsOneWidget);
    await tester.tap(moreButton);
    await tester.pumpAndSettle();

    final shareAction = find.text(ObjectHomepageText.homepageShareAction);
    expect(shareAction, findsOneWidget);
    await tester.tap(shareAction);
    await tester.pumpAndSettle();

    expect(find.byType(ForwardShareSheet), findsOneWidget);
  });
}

class _NoNetworkHttpOverrides extends HttpOverrides {}

final class _GuestHomepageSession extends AuthSessionController {
  @override
  AuthSessionState build() =>
      const AuthSessionState(status: AuthSessionStatus.guest);
}
