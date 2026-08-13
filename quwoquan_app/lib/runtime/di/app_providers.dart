// `app_providers.dart` 只保留 domain 级 barrel：不声明任何 Provider，
// 只把各 domain provider 库与跨平台防腐层入口汇总成单一 import 面。
// 新增 Provider 一律落到所属 domain 库，不要写回本文件。
export 'package:quwoquan_app/runtime/platform/platform_providers.dart'
    show
        platformTargetProvider,
        platformCapabilitiesProvider,
        fileStorageGatewayProvider,
        assistantLocalContextBridgeProvider,
        nativeAuthBridgeProvider,
        nativeShareBridgeProvider;
export 'package:quwoquan_app/runtime/di/login_dependencies.dart'
    show oneTapLoginClientProvider;
export 'package:quwoquan_app/runtime/di/ops_event_dependencies.dart'
    show appTelemetryReporterProvider;
export 'package:quwoquan_app/runtime/di/generated_operation_client_dependencies.dart'
    show cloudRuntimeEnvironmentProvider;
export 'package:quwoquan_app/runtime/di/runtime_observability_dependencies.dart'
    show appEventLogPortProvider, exceptionTelemetryPortProvider;
export 'package:quwoquan_app/runtime/observability/app_observability_ports.dart'
    show AppEventLogPort, ExceptionTelemetryPort;

export 'package:quwoquan_app/runtime/di/app_providers_app_state.dart';
export 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart';
export 'package:quwoquan_app/runtime/di/content_behavior_dependencies.dart';
export 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart';
export 'package:quwoquan_app/runtime/di/app_providers_client_sync.dart';
export 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
export 'package:quwoquan_app/runtime/di/app_providers_content_extras.dart';
export 'package:quwoquan_app/runtime/di/content_publication_epoch.dart';
export 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart';
export 'package:quwoquan_app/runtime/di/app_providers_content_runtime.dart';
export 'package:quwoquan_app/runtime/di/app_providers_content_runtime_defaults.dart';
export 'package:quwoquan_app/runtime/di/app_providers_entity_extras.dart';
export 'package:quwoquan_app/service/content_service/content/post/application/public/post_interaction_state.dart';
export 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
export 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';
export 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/user_relationship_state.dart';
export 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';
export 'package:quwoquan_app/runtime/di/app_providers_operations.dart';
export 'package:quwoquan_app/runtime/di/app_providers_rtc_facets.dart';
