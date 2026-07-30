import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/core/links/trusted_endpoint_policy.dart';
import 'package:url_launcher/url_launcher.dart';

typedef AccountRestrictionSupportOpener = Future<bool> Function(Uri uri);

/// Safe handoff for an account-restriction user to the official public site.
///
/// There is currently no canonical appeal submission operation or dedicated
/// appeal URL. This launcher therefore opens only the environment-injected
/// official Web root and never reports an appeal as submitted.
abstract interface class AccountRestrictionSupportLauncher {
  Future<bool> openOfficialSupport();
}

final class PublicWebAccountRestrictionSupportLauncher
    implements AccountRestrictionSupportLauncher {
  const PublicWebAccountRestrictionSupportLauncher({
    required this.publicWebBaseUrl,
    required this.opener,
  });

  factory PublicWebAccountRestrictionSupportLauncher.runtime() {
    return PublicWebAccountRestrictionSupportLauncher(
      publicWebBaseUrl: CloudRuntimeConfig.publicWebBaseUrl,
      opener: (uri) => launchUrl(uri, mode: LaunchMode.externalApplication),
    );
  }

  final String publicWebBaseUrl;
  final AccountRestrictionSupportOpener opener;

  @override
  Future<bool> openOfficialSupport() async {
    final destination = officialSupportDestination(publicWebBaseUrl);
    if (destination == null) return false;
    try {
      return await opener(destination);
    } catch (_) {
      return false;
    }
  }
}

Uri? officialSupportDestination(String publicWebBaseUrl) {
  final candidate = Uri.tryParse(publicWebBaseUrl.trim());
  if (candidate == null || !isUriWithinTrustedHttpsBase(candidate, candidate)) {
    return null;
  }
  return candidate;
}
