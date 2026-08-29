import 'dart:async';

// settings-canonical-exception: deferred_inset state part hosts SettingsInsetFormPageScaffold; CR-20260624-settings-page-redesign
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/presentation/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/design_system/media/app_media_image.dart';
import 'package:quwoquan_app/service/content_service/media/media_upload_session/application/public/image_pick_source.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show activePersonaContextProvider, journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show
        circleDetailCircleConfigurationCommandWriterProvider,
        circlesListCircleLifecycleCommandWriterProvider;
import 'package:quwoquan_app/runtime/di/app_providers_content_facets.dart'
    show imagePickGatewayProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/domain/circle_page_tab.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/domain/circle_edit_submit_payload.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/circle_state_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        Circle,
        CircleJoinPolicy,
        CircleSectionConfig,
        CircleSectionType,
        CircleVisibility;
part 'circle_edit_settings_page_state.dart';
part 'circle_edit_settings_page_state_helpers.dart';
part 'circle_edit_settings_page_controls.dart';

enum CircleEditSettingsTab { info, settings }

enum _CircleMediaSlot { cover, avatar }

enum _CircleMediaAction { camera, photoLibrary, remove }

class CircleEditSettingsPage extends ConsumerStatefulWidget {
  // 编辑模式的宿主对象必须在场：调用方要么已拿到圈子，要么先落缺席终态。
  // 让它在类型上非空，缺席就无法走到需要为 visibility/joinPolicy 代偿默认值的地方。
  const CircleEditSettingsPage({
    super.key,
    required this.circleId,
    required Circle this.initialCircle,
    this.initialTab = CircleEditSettingsTab.info,
    this.initialAvatarUrl,
  }) : isCreateMode = false;

  const CircleEditSettingsPage.create({
    super.key,
    this.initialTab = CircleEditSettingsTab.info,
  }) : circleId = null,
       initialCircle = null,
       initialAvatarUrl = null,
       isCreateMode = true;

  final String? circleId;
  final Circle? initialCircle;
  final CircleEditSettingsTab initialTab;
  final String? initialAvatarUrl;
  final bool isCreateMode;

  @override
  ConsumerState<CircleEditSettingsPage> createState() =>
      _CircleEditSettingsPageState();
}
