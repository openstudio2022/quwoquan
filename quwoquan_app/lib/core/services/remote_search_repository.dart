import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_search_item_view_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/models/search_hit_payload.dart';
import 'package:quwoquan_app/core/services/retrieve_request.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';

/// 结果模式接云：消费 `search-service` 的 `POST /v1/search` 统一检索结果（R-S06）。
///
/// 设计要点（端云一致性 + 单一真相源）：
/// - 请求体走 codegen 真相源：path = [SearchApiMetadata.searchQueryPath]，
///   字段名 = [SearchToolFieldNames]，`objectTypes` 取 [RetrieveTarget] wire 值
///   （`article/photo/video/...`，对齐云侧 `NormalizeTargets` 的 Target allowlist；
///   `SearchObjectType` wire 值不会被云侧识别，禁止直接外发）。
/// - 统一走 [CloudHttpClient.postJsonObject]（含鉴权头合并、状态码守卫、错误映射），
///   不自建重试 / 不裸 `http.Client`；请求头走 [CloudRequestHeaders.forPage] + codegen pageId。
/// - 响应解析为 [SearchResponse]，并透传云侧字段：`rankReasons / rankPosition /
///   coverWidth / coverHeight / connectionState / intersectionReason / relatedTerms`。
/// - 结果模式只接受云侧对象类型；本地命名空间对象（`chat.*`）不外发、不进结果。
/// - suggest 模式保留既有本地命名空间组合（联系人 / 聊天记录 / 圈子本地检索），
///   委托注入的 [_localFanout]（其内部子仓库在 remote 模式下本身已是 Remote 实现，
///   因此是「远端云对象 + 本地命名空间」的天然 composite，而非整表委托 Mock）。
/// - 错误结构化：非 2xx / 网络异常由 [CloudHttpClient] 抛出 `CloudException`（携带
///   `runtimeFailure`），本类不吞异常、不返回假数据，由上层结果页统一降级展示。
class RemoteSearchRepository implements SearchRepository {
  RemoteSearchRepository({
    required this._localFanout,
    CloudHttpClient? httpClient,
    String? baseUrl,
  }) : _httpClient = httpClient ?? CloudHttpClient(),
       _baseUrl = (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim();

  final CloudHttpClient _httpClient;
  final SearchRepository _localFanout;
  final String _baseUrl;

  @override
  Future<SearchResponse> search(SearchRequest request) async {
    final normalized = request.normalized();
    if (normalized.query.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }

    // suggest 模式：保留本地命名空间组合（chat/contact/circle 本地检索不破坏）。
    if (normalized.mode == SearchMode.suggest) {
      return _localFanout.search(normalized);
    }

    // 结果模式：当调用方显式只点名了非云侧可检索对象（如 integration.location_poi /
    // tag / web.document）时，不向 /v1/search 发起广撒网检索，直接 fail-closed 返回空，
    // 避免误触云侧 DefaultResultTargets 全量扇出。
    if (normalized.objectTypes.isNotEmpty &&
        !normalized.objectTypes.any(_isCloudRetrievable)) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }

    final targets = _cloudTargets(normalized);
    if (targets.isEmpty) {
      return SearchResponse(
        request: normalized,
        sections: const <SearchSection>[],
      );
    }

    final uri = Uri.parse('$_baseUrl${SearchApiMetadata.searchQueryPath}');
    final body = <String, dynamic>{
      SearchToolFieldNames.query: normalized.query,
      SearchToolFieldNames.mode: normalized.mode.wireValue,
      SearchToolFieldNames.objectTypes: targets
          .map((target) => target.wireValue)
          .toList(growable: false),
      SearchToolFieldNames.limit: normalized.limit,
    };

    final decoded = await _httpClient.postJsonObject(
      uri,
      headers: CloudRequestHeaders.forPage(SearchRequestPageIds.searchQuery),
      body: body,
      context: SearchApiMetadata.searchQueryOperation,
    );

    return _responseFromCloud(normalized, decoded);
  }

  /// 云侧 `/v1/search` 仅认 [RetrieveTarget] 的 wire 值。复用 [RetrieveRequest] 的
  /// 单一真相源映射后剔除 `chat`（本地命名空间，不外发），保证结果模式只取云侧对象。
  List<RetrieveTarget> _cloudTargets(SearchRequest request) {
    return RetrieveRequest.fromSearchRequest(request).targets
        .where((target) => target != RetrieveTarget.chat)
        .toList(growable: false);
  }

  bool _isCloudRetrievable(SearchObjectType type) {
    switch (type) {
      case SearchObjectType.contentPost:
      case SearchObjectType.userProfile:
      case SearchObjectType.entityHomepage:
      case SearchObjectType.circleCircle:
      case SearchObjectType.circleGroup:
      case SearchObjectType.locationPlace:
        return true;
      case SearchObjectType.chatContact:
      case SearchObjectType.chatConversation:
      case SearchObjectType.chatMessage:
      case SearchObjectType.webDocument:
      case SearchObjectType.tag:
      case SearchObjectType.integrationLocationPoi:
        return false;
    }
  }

  SearchResponse _responseFromCloud(
    SearchRequest request,
    Map<String, dynamic> decoded,
  ) {
    final rawHits = decoded['hits'];
    final hits = <SearchHit>[];
    if (rawHits is List) {
      for (final raw in rawHits) {
        if (raw is! Map) {
          continue;
        }
        final hit = _hitFromCloud(Map<String, dynamic>.from(raw));
        if (hit != null) {
          hits.add(hit);
        }
      }
    }

    // 按对象类型聚合为分区（保留云侧 rankPosition 命中顺序）；结果页消费 `hits` 平铺。
    final byType = <SearchObjectType, List<SearchHit>>{};
    for (final hit in hits) {
      byType.putIfAbsent(hit.objectType, () => <SearchHit>[]).add(hit);
    }
    final sections = byType.entries
        .map(
          (entry) => SearchSection(
            id: entry.key.wireValue,
            title:
                SearchRegistry.entryFor(entry.key)?.label ??
                entry.key.wireValue,
            objectTypes: <SearchObjectType>[entry.key],
            hits: entry.value,
            resolvedFrom: SearchResolvedFrom.remote,
          ),
        )
        .toList(growable: false);

    return SearchResponse(
      request: request,
      sections: sections,
      degradeSignals: _degradeSignals(decoded['degradeSignals']),
      relatedTerms: _stringList(decoded['relatedTerms']),
    );
  }

  /// 单条 `RetrieveHit` → [SearchHit]。target 通过 [RetrieveTargetRegistry] 落到
  /// [SearchObjectType]；本地命名空间对象（chat.*）一律丢弃。
  SearchHit? _hitFromCloud(Map<String, dynamic> map) {
    final target = RetrieveTarget.fromWire(map['target']?.toString());
    if (target == null) {
      return null;
    }
    final entry = RetrieveTargetRegistry.entryFor(target);
    if (entry == null) {
      return null;
    }
    final objectType = entry.objectType;
    if (!_isCloudRetrievable(objectType)) {
      return null;
    }

    final objectId = map['objectId']?.toString().trim() ?? '';
    if (objectId.isEmpty) {
      return null;
    }
    final title = map['title']?.toString().trim() ?? '';
    final snippet = map['snippet']?.toString();
    final payload = map['payload'] is Map
        ? Map<String, dynamic>.from(map['payload'] as Map)
        : <String, dynamic>{};

    // 云侧排序透明化 + 封面真实宽高（coverWidth/coverHeight 可能在 hit 顶层或 payload）。
    final rankReasons = _rankReasonLabels(map['rankReasons']);
    final rankPosition = (map['rankPosition'] as num?)?.toInt();
    final coverWidth = _dimension(map['coverWidth'] ?? payload['coverWidth']);
    final coverHeight = _dimension(
      map['coverHeight'] ?? payload['coverHeight'],
    );

    // 交集 / 连接态：由 search-service 从统一交集真相源附着，端侧只透传不合成。
    final connectionState = map['connectionState']?.toString();
    final intersectionReason = map['intersectionReason'];

    final SearchHitPayload hitPayload;
    if (objectType == SearchObjectType.contentPost) {
      final merged = <String, dynamic>{
        ...payload,
        'postId': objectId,
        if (title.isNotEmpty) 'title': title,
        if (snippet != null && snippet.isNotEmpty) 'summary': snippet,
        // contentType 以 target 派生为准（article/image/video），避免 payload 漂移。
        'contentType': entry.contentType,
        if (connectionState != null && connectionState.isNotEmpty)
          'connectionState': connectionState,
        if (intersectionReason is Map)
          'intersectionReason': Map<String, dynamic>.from(intersectionReason),
      };
      hitPayload = SearchHitPayloadContentPost(
        PostSearchItemView.fromMap(merged),
      );
    } else {
      hitPayload = SearchHitPayloadWireMap(<String, dynamic>{
        ...payload,
        'objectId': objectId,
        if (title.isNotEmpty) 'title': title,
        'snippet': ?snippet,
        if (connectionState != null && connectionState.isNotEmpty)
          'connectionState': connectionState,
        if (intersectionReason is Map)
          'intersectionReason': Map<String, dynamic>.from(intersectionReason),
      });
    }

    return SearchHit(
      objectType: objectType,
      objectId: objectId,
      title: title.isNotEmpty ? title : objectId,
      subtitle: _firstNonEmpty(<Object?>[
        payload['subtitle'],
        payload['placeName'],
        payload['circleName'],
        payload['authorDisplayName'],
      ]),
      snippet: snippet,
      resolvedFrom: SearchResolvedFrom.remote,
      matchedField: _evidenceField(map['evidence']),
      payload: hitPayload,
      rankReasons: rankReasons,
      rankPosition: rankPosition,
      coverWidth: coverWidth,
      coverHeight: coverHeight,
    );
  }

  /// Go `Reason` 结构无 json tag，wire 形如 `{"Code":..,"Label":..,"Weight":..}`，
  /// 同时兼容小写键，取 `Label` 作为人类可读排序理由。
  List<String> _rankReasonLabels(Object? raw) {
    if (raw is! List) {
      return const <String>[];
    }
    final labels = <String>[];
    for (final item in raw) {
      if (item is! Map) {
        continue;
      }
      final label = (item['Label'] ?? item['label'] ?? '').toString().trim();
      if (label.isNotEmpty) {
        labels.add(label);
      }
    }
    return labels;
  }

  double? _dimension(Object? value) {
    if (value == null) {
      return null;
    }
    final parsed = value is num
        ? value.toDouble()
        : double.tryParse(value.toString());
    if (parsed == null || parsed <= 0) {
      return null;
    }
    return parsed;
  }

  String? _evidenceField(Object? raw) {
    if (raw is! List || raw.isEmpty) {
      return null;
    }
    final first = raw.first;
    if (first is Map) {
      final field = first['field']?.toString().trim();
      if (field != null && field.isNotEmpty) {
        return field;
      }
    }
    return null;
  }

  List<SearchDegradeSignal> _degradeSignals(Object? raw) {
    if (raw is! List) {
      return const <SearchDegradeSignal>[];
    }
    final signals = <SearchDegradeSignal>[];
    for (final item in raw) {
      if (item is! Map) {
        continue;
      }
      final code = (item['code'] ?? item['Code'] ?? '').toString().trim();
      final message = (item['message'] ?? item['Message'] ?? '')
          .toString()
          .trim();
      if (code.isEmpty && message.isEmpty) {
        continue;
      }
      signals.add(SearchDegradeSignal(code: code, message: message));
    }
    return signals;
  }

  List<String> _stringList(Object? raw) {
    if (raw is! List) {
      return const <String>[];
    }
    return raw
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }

  String? _firstNonEmpty(List<Object?> values) {
    for (final value in values) {
      final text = value?.toString().trim();
      if (text != null && text.isNotEmpty) {
        return text;
      }
    }
    return null;
  }
}
