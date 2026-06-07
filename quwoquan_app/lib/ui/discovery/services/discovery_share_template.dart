import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/models/discovery_presentation_wire.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/content/models/content_route_models.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

ContentShareTemplate buildDiscoveryShareTemplate({
  required PostBaseDto post,
  required DiscoveryPresentationWire? wire,
  required bool enableIdentityTemplate,
}) {
  final circleName = wire?.circleName ?? '';
  final surfaceView = ContentSurfaceViewMapper.fromDto(
    post,
    wire: wire?.toWireMap(),
  );
  return ContentShareTemplateBuilder.build(
    surfaceView: surfaceView,
    enableIdentityTemplate: enableIdentityTemplate,
    visibility: wire?.visibility ?? 'public',
    circleNames: circleName.isEmpty ? const <String>[] : <String>[circleName],
  );
}

String discoverySourceCircleName(WidgetRef ref, String postId) {
  return ref.read(contentRepositoryProvider).discoveryPresentationWireForPost(postId)?.circleName ?? '';
}
