import 'package:quwoquan_app/app_bootstrap.dart';

import 'alpha_cloud_composition.dart';

Future<void> main() async {
  await runQuwoquanApp(providerScopeOverrides: buildAlphaCloudOverrides());
}
