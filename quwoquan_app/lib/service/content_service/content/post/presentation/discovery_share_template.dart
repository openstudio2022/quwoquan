import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_template.dart';

ContentShareTemplate buildDiscoveryShareTemplate({
  required ContentPostViewData post,
  required bool enableIdentityTemplate,
  List<String> tags = const <String>[],
  String visibility = 'public',
  PublicContentLinkBuilder? publicLinks,
}) {
  final surfaceView = ContentSurfaceViewMapper.fromDto(post).copyWith(
    tags: List<String>.unmodifiable(
      tags.map((tag) => tag.trim()).where((tag) => tag.isNotEmpty),
    ),
  );
  return ContentShareTemplateBuilder.build(
    surfaceView: surfaceView,
    enableIdentityTemplate: enableIdentityTemplate,
    visibility: visibility,
    publicLinks: publicLinks,
  );
}
