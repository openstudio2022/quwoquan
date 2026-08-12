import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/ios_selection_page_components.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_write_target_reader.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_action_tracker.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_command_writer.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage_status_report/application/public/homepage_status_report_query_reader.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_continuation.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/auth/homepage_write_access.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show HomepageStatusReportStatus, HomepageStatusReportView;
import 'package:quwoquan_runtime_errors/runtime_errors.dart';
import 'package:uuid/uuid.dart';

part 'homepage_status_report_page_state.dart';

class HomepageStatusReportPage extends ConsumerStatefulWidget {
  const HomepageStatusReportPage({
    super.key,
    required this.homepageId,
    required this.writeTargetReader,
    required this.commandWriter,
    required this.queryReader,
    required this.actionTracker,
  });

  final String homepageId;
  final HomepageWriteTargetReader writeTargetReader;
  final HomepageStatusReportCommandWriter commandWriter;
  final HomepageStatusReportQueryReader queryReader;
  final HomepageStatusReportActionTracker actionTracker;

  @override
  ConsumerState<HomepageStatusReportPage> createState() =>
      _HomepageStatusReportPageState();
}
