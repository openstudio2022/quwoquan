import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_view_data.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/application/public/homepage_route_models.dart';

Future<HomepageCanonicalReference?> pickArticleEntityMentionHomepage(
  BuildContext context,
) async {
  final result = await context.push<HomepagePickerSelectionResult>(
    AppRoutePaths.homepagePicker(),
  );
  return result?.selection;
}
