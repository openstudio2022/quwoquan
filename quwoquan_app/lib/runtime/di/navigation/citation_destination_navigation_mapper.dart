import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/citation_destination_resolver.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';

final class InternalCitationNavigationTarget {
  const InternalCitationNavigationTarget({
    required this.routePath,
    required this.deepLink,
  });

  final String routePath;
  final String deepLink;
}

/// 把纯 citation identity 映射为 metadata/codegen 生成的导航目标。
abstract final class CitationDestinationNavigationMapper {
  CitationDestinationNavigationMapper._();

  static InternalCitationNavigationTarget? resolveInternal(
    InternalCitationDestination destination,
  ) {
    final routePath = AppLinkTemplates.citationInternalRoutePath(
      destination.objectTypeRef,
      destination.objectId,
    );
    final deepLink = AppLinkTemplates.citationInternalDeepLink(
      destination.objectTypeRef,
      destination.objectId,
    );
    if (routePath.isEmpty || deepLink.isEmpty) {
      return null;
    }
    return InternalCitationNavigationTarget(
      routePath: routePath,
      deepLink: deepLink,
    );
  }
}
