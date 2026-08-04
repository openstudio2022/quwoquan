import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_view_data.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_action_observability.dart';
import 'package:quwoquan_app/entity/entity_homepage/homepage/domain/homepage_write_access.dart';

part 'homepage_status_report_page_state.dart';

class HomepageStatusReportPage extends ConsumerStatefulWidget {
  const HomepageStatusReportPage({super.key, required this.homepageId});

  final String homepageId;

  @override
  ConsumerState<HomepageStatusReportPage> createState() =>
      _HomepageStatusReportPageState();
}
