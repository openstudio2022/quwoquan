import 'dart:async';

// settings-canonical-exception: deferred_inset state part hosts SettingsInsetFormPageScaffold; CR-20260624-settings-page-redesign
import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/components/media/picker/image_pick_gateway.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/circle/models/circle_page_tab.dart';
import 'package:quwoquan_app/ui/circle/models/circle_edit_submit_payload.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
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
  const CircleEditSettingsPage({
    super.key,
    required this.circleId,
    required this.initialCircle,
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
