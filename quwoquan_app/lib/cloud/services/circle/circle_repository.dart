import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/models/circle_detail_payload.dart';
import 'package:quwoquan_app/cloud/services/circle/mock/circle_mock_data.dart';
import 'package:quwoquan_cloud_contracts/circle_repository.dart'
    show CircleRepository, kHomeCircleDiscoveryFeedDefaultLimit;

export 'package:quwoquan_cloud_contracts/circle_repository.dart'
    show CircleRepository, kHomeCircleDiscoveryFeedDefaultLimit;

part 'circle_repository_mock.dart';
part 'circle_repository_remote.dart';

String? _normalizeCircleFeedType(String? type) {
  final normalized = (type ?? '').trim().toLowerCase();
  switch (normalized) {
    case '':
      return null;
    case 'photo':
      return 'image';
    case 'note':
      return 'article';
    default:
      return normalized;
  }
}

List<PostBaseDto> _decodeCircleFeedMaps(Iterable<Map<String, dynamic>> items) {
  final out = <PostBaseDto>[];
  for (final m in items) {
    try {
      out.add(postBaseDtoFromMap(Map<String, dynamic>.from(m)));
    } catch (_) {
      // 跳过无法映射为 PostBaseDto 的 wire 行（与旧版尽力解析一致）
    }
  }
  return out;
}
