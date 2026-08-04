// `app_providers.dart` 只保留 domain 级 barrel：不声明任何 Provider，
// 只把各 domain provider 库与跨平台防腐层入口汇总成单一 import 面。
// 新增 Provider 一律落到所属 domain 库，不要写回本文件。
export 'package:quwoquan_app/core/platform/platform_providers.dart'
    show
        platformTargetProvider,
        platformCapabilitiesProvider,
        fileStorageGatewayProvider,
        assistantLocalContextBridgeProvider,
        nativeAuthBridgeProvider,
        nativeShareBridgeProvider;
export 'package:quwoquan_app/core/di/login_dependencies.dart'
    show oneTapLoginClientProvider;
export 'package:quwoquan_app/core/di/ops_event_dependencies.dart'
    show appTelemetryReporterProvider;
export 'package:quwoquan_app/core/di/generated_operation_client_dependencies.dart'
    show cloudRuntimeEnvironmentProvider;

export 'package:quwoquan_app/core/providers/app_providers_app_state.dart';
export 'package:quwoquan_app/core/providers/app_providers_chat_search.dart';
export 'package:quwoquan_app/core/providers/app_providers_circle_facets.dart';
export 'package:quwoquan_app/core/providers/app_providers_client_sync.dart';
export 'package:quwoquan_app/core/providers/app_providers_content_extras.dart';
export 'package:quwoquan_app/core/providers/app_providers_content_facets.dart';
export 'package:quwoquan_app/core/providers/app_providers_content_runtime.dart';
export 'package:quwoquan_app/core/providers/app_providers_content_runtime_defaults.dart';
export 'package:quwoquan_app/core/providers/app_providers_entity_extras.dart';
export 'package:quwoquan_app/core/providers/app_providers_interaction_state.dart';
export 'package:quwoquan_app/core/providers/app_providers_operations.dart';
export 'package:quwoquan_app/core/providers/app_providers_rtc_facets.dart';
export 'package:quwoquan_app/core/providers/app_providers_travel.dart';
