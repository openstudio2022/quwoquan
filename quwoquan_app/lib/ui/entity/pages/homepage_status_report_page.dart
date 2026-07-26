import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_action_observability.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_write_access.dart';

part 'homepage_status_report_page_state.dart';

class HomepageStatusReportPage extends ConsumerStatefulWidget {
  const HomepageStatusReportPage({super.key, required this.homepageId});

  final String homepageId;

  @override
  ConsumerState<HomepageStatusReportPage> createState() =>
      _HomepageStatusReportPageState();
}
