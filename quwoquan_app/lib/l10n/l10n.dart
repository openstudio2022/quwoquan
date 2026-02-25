export 'package:quwoquan_app/l10n/app_localizations.dart';

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';

extension AppLocalizationsX on BuildContext {
  AppLocalizations get l10n => AppLocalizations.of(this);
}
