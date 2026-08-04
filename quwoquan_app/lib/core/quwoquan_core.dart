// Core exports file for quwoquan_app
// This file exports all core functionality

// Core functionality
export 'core.dart' show MediaItem;

// Emoji (public library + analytics)
export 'emoji/emoji_analytics.dart';
export 'emoji/emoji_catalog.dart';
export 'emoji/emoji_providers.dart';
export 'emoji/emoji_repository.dart';

// Constants
export 'constants/ui_text_constants.dart';
export 'constants/content_type_constants.dart';
export 'constants/app_strings.dart';
export 'constants/design_semantic_constants.dart';
export 'constants/search_semantic_constants.dart';
export 'constants/settings_semantic_constants.dart';
export 'constants/app_concept_constants.dart';
export 'constants/z_index_constants.dart';

// Design System
export 'design_system/theme/app_theme.dart';
export 'design_system/colors/app_colors.dart';
export 'design_system/spacing/app_spacing.dart';
export 'design_system/spacing/recovery_surface_spacing.dart';
export 'design_system/spacing/spacing_extensions.dart';
export 'design_system/typography/app_typography.dart';
export 'design_system/icons/app_custom_icons.dart';

// Core widgets
export 'widgets/app_action_sheet.dart';
export 'widgets/conversation_sheet.dart';
export 'widgets/app_modal_presenter.dart';
export 'widgets/app_modal_surface.dart';
export 'widgets/app_list_page_semantics.dart';
export 'widgets/app_search_field.dart';
export 'widgets/app_terminal_viewport.dart';
export 'widgets/error_states/app_error_states.dart';
export 'widgets/app_request_feedback.dart';
export 'widgets/ios_selection_page_components.dart';
export 'widgets/web_page_max_width_frame.dart';

// Providers
export 'design_system/providers/theme_provider.dart';
export 'providers/app_providers.dart';
export 'package:quwoquan_app/app/providers/app_state_provider.dart';
export 'package:quwoquan_app/app/providers/accessibility_provider.dart';
export 'package:quwoquan_app/content/media/media_asset/application/video_force_dark_provider.dart'
    show
        VideoForceDarkState,
        VideoForceDarkNotifier,
        videoForceDarkProvider,
        BottomNavHiddenState,
        BottomNavHiddenNotifier,
        bottomNavHiddenProvider;
export 'package:quwoquan_app/content/content/post/application/discovery_state.dart';

// Services
export 'auth/auth_session.dart';
export 'auth/auth_gate.dart';
export 'auth/auth_continuation.dart';
export 'auth/auth_legal_config.dart';
export 'platform/one_tap_login_native_bridge.dart';
export 'errors/ui_error_semantics.dart';
export 'package:quwoquan_app/core/errors/runtime_error_display.dart'
    show
        ensureRetryUiErrorSemantic,
        runtimeErrorDisplayMessage,
        runtimeErrorSemantic;
export 'services/app_page_load_arbiter.dart';

// Utils
export 'utils/chat_time_formatter.dart';

// Models
export 'package:quwoquan_app/core/models/object_relation_edge_type.dart';
export 'package:quwoquan_app/core/models/post_models.dart';
export 'package:quwoquan_app/core/models/search_models.dart';
export 'package:quwoquan_app/core/models/story_models.dart';
export 'package:quwoquan_app/core/models/user_models.dart';
