// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: tools/codegen_app_metadata/content_dtos_barrel_codegen.go
// Regenerate: make codegen-app (from quwoquan_service)

export 'post_base_dto.dart';
export 'comment_dto.g.dart';
export 'post_search_item_view_dto.g.dart';
export 'report_create_request_wire.g.dart';
export 'post_read_surface_id.g.dart';
export 'article_detail_wire_keys.g.dart';
export 'article_card_wire_keys.g.dart';
export 'article_block_wire_keys.g.dart';
export 'content_post_immersive_wire_keys.g.dart';
export 'content_app_config_client_dto.g.dart';
export 'content_post_detail_wire_dto.g.dart';
export 'post_read_presentation.g.dart';
export 'photo_post_dto.g.dart';
export 'video_post_dto.g.dart';
export 'article_post_dto.g.dart';
export 'moment_post_dto.g.dart';
export 'feed_item_dto.g.dart';
export 'content_post_mutation_wires.g.dart';
export 'content_media_init_upload_response_dto.g.dart';
export 'content_media_complete_upload_response_dto.g.dart';
export 'content_media_asset_wire_dto.g.dart';
export 'content_video_cover_selection_wire_dto.g.dart';
export 'content_article_summary_generate_response_dto.g.dart';
export 'content_recommendation_response_dto.g.dart';

import 'package:quwoquan_app/cloud/runtime/generated/content/photo_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/video_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/article_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/moment_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';

/// contentType に応じて対応するサブクラスにディスパッチする。
/// 按 contentType 分发到对应子类型 DTO。
///
/// 支持的 contentType 值：
/// - image / photo → PhotoPostDto
/// - video → VideoPostDto
/// - article → ArticlePostDto
/// - micro / moment → MomentPostDto
PostBaseDto postBaseDtoFromMap(Map<String, dynamic> m) {
  final contentType = m['contentType']?.toString() ??
      m['type']?.toString() ??
      m['category']?.toString() ??
      '';
  switch (contentType) {
    case 'video':
      return VideoPostDto.fromMap(m);
    case 'article':
      return ArticlePostDto.fromMap(m);
    case 'micro':
    case 'moment':
      return MomentPostDto.fromMap(m);
    case 'image':
    case 'photo':
    default:
      return PhotoPostDto.fromMap(m);
  }
}
