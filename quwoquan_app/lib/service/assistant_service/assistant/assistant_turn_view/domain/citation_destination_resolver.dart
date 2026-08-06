import 'package:quwoquan_app/runtime/shell/navigation/generated/link_templates.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show
        CitationDestination,
        CitationDestinationKind,
        parseCitationDestinationKindStrict;

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
    switch (destination.kind) {
      case CitationDestinationKind.internal:
        return _resolveInternal(destination);
      case CitationDestinationKind.external:
        return _resolveExternal(destination);
      case CitationDestinationKind.unknown:
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
        !uri.hasScheme ||
        uri.host.isEmpty ||
        uri.scheme.toLowerCase() != 'https') {
      return null;
    }
    return ExternalCitationDestination(uri.removeFragment());
  }
}

/// 把未定型 transport object 收口为 canonical citation destination。
CitationDestination citationDestinationFromWireObject(Object? raw) {
  if (raw is! Map) {
    throw const FormatException('citation destination must be an object');
  }
  final object = <String, Object?>{};
  for (final entry in raw.entries) {
    if (entry.key is! String) {
      throw const FormatException('citation destination keys must be strings');
    }
    object[entry.key as String] = entry.value;
  }
  return CitationDestination(
    kind: parseCitationDestinationKindStrict((object['kind'] ?? '').toString()),
    objectTypeRef: object['objectTypeRef']?.toString(),
    objectId: object['objectId']?.toString(),
    url: object['url']?.toString(),
  );
}

/// 引用去重 key 的唯一入口。非法 destination 返回空字符串，调用方必须丢弃，
/// 不得退回 title/source 形成不可导航的第二引用契约。
String citationReferenceKey(
  CitationDestination destination, {
  String source = '',
  String title = '',
}) {
  final resolved = CitationDestinationResolver.resolve(destination);
  if (resolved is ExternalCitationDestination) {
    return resolved.uri.toString();
  }
  if (resolved is InternalCitationDestination) {
    return '${resolved.objectTypeRef}:${resolved.objectId}';
  }
  return '';
}

/// 只有 destination 可解析时才允许展示或交互。
bool hasUsableCitationDestination(
  CitationDestination destination, {
  String title = '',
  String source = '',
}) {
  return CitationDestinationResolver.resolve(destination) != null;
}
