import 'dart:developer' as developer;

import 'package:quwoquan_app/tag/tag/tag_node_view/application/tag_catalog_query.dart';
import 'package:quwoquan_app/tag/tag/tag_node_view/domain/administrative_tag_path.dart';

/// 把发布定位解析成行政区标签 `geoTagRef`。
///
/// 端侧只负责把地址拆成行政区链并拼出候选路径；哪一条真实存在由 tag-service
/// `ResolveTag` 判定，标签树本身不进 App 包。候选按「区县 → 市 → 省 → 国」由细到粗
/// 依次尝试，第一条命中即返回，因此标签树未覆盖到区县时会自然退化到市级而不是整体失败。
///
/// 全部候选都不存在时返回 null：宁可没有 `geoTagRef`，不臆造一个不在标签树里的路径。
final class GeoTagRefResolver {
  const GeoTagRefResolver(this._catalog, {this.maxCandidates = 4});

  final TagCatalogQuery _catalog;

  /// 单次发布最多消耗的 resolve 次数，避免为一个可选字段打满往返。
  final int maxCandidates;

  /// 由 POI 的展示名与地址解析行政区标签。
  ///
  /// [address] 是 provider 返回的结构化程度最低但最完整的行政区来源；[name] 只在
  /// 地址缺失时兜底（部分 provider 的 POI 名本身就带省市前缀）。
  Future<String?> resolveFromPoi({String? address, String? name}) {
    final source = (address ?? '').trim().isNotEmpty
        ? address!.trim()
        : (name ?? '').trim();
    if (source.isEmpty) return Future<String?>.value();
    return resolveFromAddress(source);
  }

  Future<String?> resolveFromAddress(String address) async {
    final candidates = administrativeTagRefCandidatesFromAddress(address);
    if (candidates.isEmpty) return null;
    for (final candidate in candidates.take(maxCandidates)) {
      if (await _exists(candidate)) return candidate;
    }
    return null;
  }

  Future<bool> _exists(String tagRef) async {
    try {
      final resolved = await _catalog.resolveTag(tagRef);
      return resolved.tagRef == tagRef;
    } catch (error) {
      // tag_not_found 是候选链上的正常结果，不是故障；网络类失败同样只让本次
      // geoTagRef 缺失，绝不阻断发布。
      developer.log(
        'geo tagRef candidate unresolved',
        name: 'GeoTagRefResolver',
        error: error,
      );
      return false;
    }
  }
}
