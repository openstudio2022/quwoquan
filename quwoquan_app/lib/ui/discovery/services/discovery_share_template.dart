import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

ContentShareTemplate buildDiscoveryShareTemplate({
  required PostBaseDto post,
  required DiscoveryPresentationWire? wire,
  required bool enableIdentityTemplate,
}) {
  final surfaceView = ContentSurfaceViewMapper.fromDto(
    post,
    wire: wire?.toWireMap(),
  );
  return ContentShareTemplateBuilder.build(
    surfaceView: surfaceView,
    enableIdentityTemplate: enableIdentityTemplate,
    visibility: wire?.visibility ?? 'public',
  );
}
