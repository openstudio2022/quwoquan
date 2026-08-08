import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_legal_config.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/shell/legal/legal_document_page.dart';

enum LegalDocumentRouteKind {
  userAgreement,
  privacyPolicy,
  permissions,
  thirdPartySdkList,
}

/// Runtime-shell owner for mapping a legal route identity to its document.
class LegalDocumentPageRouteHost extends StatelessWidget {
  const LegalDocumentPageRouteHost({
    super.key,
    required this.kind,
    required this.journeyEventTracker,
  });

  final LegalDocumentRouteKind kind;
  final JourneyEventTracker journeyEventTracker;

  @override
  Widget build(BuildContext context) {
    final (title, url) = switch (kind) {
      LegalDocumentRouteKind.userAgreement => (
        FoundationText.userAgreement,
        AuthLegalConfig.userAgreementUrl,
      ),
      LegalDocumentRouteKind.privacyPolicy => (
        FoundationText.privacyPolicy,
        AuthLegalConfig.privacyPolicyUrl,
      ),
      LegalDocumentRouteKind.permissions => (
        FoundationText.permissionsStatement,
        AuthLegalConfig.permissionsUrl,
      ),
      LegalDocumentRouteKind.thirdPartySdkList => (
        FoundationText.thirdPartySdkList,
        AuthLegalConfig.thirdPartySdkListUrl,
      ),
    };
    return LegalDocumentPage(
      title: title,
      url: url,
      journeyEventTracker: journeyEventTracker,
    );
  }
}
