import 'package:flutter/widgets.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/application/entity/homepage_view_data.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';

Future<HomepageCanonicalReference?> pickArticleEntityMentionHomepage(
  BuildContext context,
) async {
  final result = await context.push<HomepagePickerSelectionResult>(
    AppRoutePaths.homepagePicker(),
  );
  return result?.selection;
}
