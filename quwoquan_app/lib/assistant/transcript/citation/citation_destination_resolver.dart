import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_cloud_api_wire.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/link_templates.g.dart';

sealed class ResolvedCitationDestination {
  const ResolvedCitationDestination();
}

final class InternalCitationDestination extends ResolvedCitationDestination {
  const InternalCitationDestination({
    required this.objectTypeRef,
    required this.objectId,
    required this.routePath,
    required this.deepLink,
  });

  final String objectTypeRef;
  final String objectId;
  final String routePath;
  final String deepLink;
}

final class ExternalCitationDestination extends ResolvedCitationDestination {
  const ExternalCitationDestination(this.uri);

  final Uri uri;
}

/// 所有助手/搜索 citation 的唯一 destination 解析入口。
///
/// 站内 path/deep link 由 `link_templates.yaml` codegen，站外仅接受绝对 HTTPS URL；
/// 任何未知 object type、空标识或非法 URL 都返回 null，调用方不得尝试默认 post 回退。
abstract final class CitationDestinationResolver {
  CitationDestinationResolver._();

  static ResolvedCitationDestination? resolve(CitationDestination destination) {
    switch (destination.kind?.trim()) {
      case 'internal':
        return _resolveInternal(destination);
      case 'external':
        return _resolveExternal(destination);
      default:
        return null;
    }
  }

  static InternalCitationDestination? _resolveInternal(
    CitationDestination destination,
  ) {
    final objectTypeRef = destination.objectTypeRef?.trim() ?? '';
    final objectId = destination.objectId?.trim() ?? '';
    if (objectTypeRef.isEmpty || objectId.isEmpty) {
      return null;
    }
    final routePath = AppLinkTemplates.citationInternalRoutePath(
      objectTypeRef,
      objectId,
    );
    final deepLink = AppLinkTemplates.citationInternalDeepLink(
      objectTypeRef,
      objectId,
    );
    if (routePath.isEmpty || deepLink.isEmpty) {
      return null;
    }
    return InternalCitationDestination(
      objectTypeRef: objectTypeRef,
      objectId: objectId,
      routePath: routePath,
      deepLink: deepLink,
    );
  }

  static ExternalCitationDestination? _resolveExternal(
    CitationDestination destination,
  ) {
    final uri = Uri.tryParse(destination.url?.trim() ?? '');
    if (uri == null ||
        !uri.isAbsolute ||
        uri.host.isEmpty ||
        uri.scheme.toLowerCase() != 'https') {
      return null;
    }
    return ExternalCitationDestination(uri.replace(fragment: ''));
  }
}
