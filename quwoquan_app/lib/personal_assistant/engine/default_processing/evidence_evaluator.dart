import 'package:quwoquan_app/personal_assistant/contracts/run_artifacts.dart';

class EvidenceEvaluationResult {
  const EvidenceEvaluationResult({
    this.entries = const <EvidenceLedgerEntry>[],
    this.coverageScore = 0,
    this.authorityScore = 0,
    this.relevanceScore = 0,
    this.freshnessHours = 0,
    this.status = 'retry',
    this.passed = false,
    this.authoritySatisfied = false,
    this.freshnessSatisfied = false,
    this.evidenceRequired = false,
    this.coveredDimensions = const <String>[],
    this.coveredQueryTaskIds = const <String>[],
    this.blockingDimensions = const <String>[],
    this.missingDimensions = const <String>[],
    this.summary = '',
  });

  final List<EvidenceLedgerEntry> entries;
  final double coverageScore;
  final double authorityScore;
  final double relevanceScore;
  final int freshnessHours;
  final String status;
  final bool passed;
  final bool authoritySatisfied;
  final bool freshnessSatisfied;
  final bool evidenceRequired;
  final List<String> coveredDimensions;
  final List<String> coveredQueryTaskIds;
  final List<String> blockingDimensions;
  final List<String> missingDimensions;
  final String summary;

  Map<String, dynamic> toJson() => <String, dynamic>{
    'coverageScore': coverageScore,
    'authorityScore': authorityScore,
    'relevanceScore': relevanceScore,
    'freshnessHours': freshnessHours,
    'status': status,
    'passed': passed,
    'authoritySatisfied': authoritySatisfied,
    'freshnessSatisfied': freshnessSatisfied,
    'evidenceRequired': evidenceRequired,
    'coveredDimensions': coveredDimensions,
    'coveredQueryTaskIds': coveredQueryTaskIds,
    'blockingDimensions': blockingDimensions,
    'missingDimensions': missingDimensions,
    'summary': summary,
  };
}

class DefaultEvidenceEvaluator {
  const DefaultEvidenceEvaluator();

  List<EvidenceLedgerEntry> buildLedger({
    required String domainId,
    required List<Map<String, dynamic>> toolResults,
    required SlotStateSnapshot slotState,
    required Map<String, dynamic> retrievalPolicy,
    DateTime? now,
  }) {
    final collected = <EvidenceLedgerEntry>[];
    final seenUrls = <String>{};
    final timestamp = (now ?? DateTime.now()).toIso8601String();
    final globalAuthorityDomains =
        (retrievalPolicy['authorityDomains'] as List?)
            ?.map((item) => item.toString().trim().toLowerCase())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    for (final item in toolResults) {
      final toolName = (item['toolName'] as String?)?.trim() ?? '';
      final data =
          (item['data'] as Map?)?.cast<String, dynamic>() ??
          const <String, dynamic>{};
      final authorityDomains = <String>{
        ...globalAuthorityDomains,
        ...((data['authorityDomains'] as List?)
                ?.map((entry) => entry.toString().trim().toLowerCase())
                .where((entry) => entry.isNotEmpty) ??
            const Iterable<String>.empty()),
      }.toList(growable: false);
      final references = _extractReferences(
        toolName: toolName,
        data: data,
        retrievedAt: timestamp,
      );
      for (final ref in references) {
        final url = (ref['url'] as String?)?.trim() ?? '';
        if (url.isEmpty || !seenUrls.add(url)) continue;
        final title = (ref['title'] as String?)?.trim() ?? '';
        final host = _hostOf(url);
        final sourceTier =
            (ref['sourceTier'] as String?)?.trim().isNotEmpty == true
            ? (ref['sourceTier'] as String).trim()
            : _resolveSourceTier(
                host: host,
                authorityDomains: authorityDomains,
              );
        final queryTaskId = _stringValue(ref['queryTaskId']);
        final dimension = _stringValue(ref['dimension']);
        final slotContributions = _buildSlotContributions(
          slotState: slotState,
          title: title,
          url: url,
          snippet: _stringValue(ref['snippet']),
        );
        collected.add(
          EvidenceLedgerEntry(
            evidenceId: _buildEvidenceId(
              domainId: domainId,
              toolName: toolName,
              queryTaskId: queryTaskId,
              url: url,
            ),
            domainId: domainId,
            dimension: dimension,
            queryTaskId: queryTaskId,
            title: title.isNotEmpty ? title : host,
            url: url,
            sourceHost: host,
            sourceTier: sourceTier,
            freshnessHours:
                _intValue(ref['freshnessHours']) ??
                _intValue(data['freshnessHours']) ??
                0,
            authorityScore:
                _doubleValue(ref['authorityScore']) ??
                _doubleValue(data['authorityScore']) ??
                _estimateAuthorityScore(
                  sourceTier: sourceTier,
                  host: host,
                  authorityDomains: authorityDomains,
                ),
            relevanceScore:
                _doubleValue(ref['relevanceScore']) ??
                _doubleValue(data['qualityScore']) ??
                (title.isNotEmpty ? 0.72 : 0.56),
            slotContributions: slotContributions,
            snippet: _stringValue(ref['snippet']),
            retrievedAt: _stringValue(ref['retrievedAt']).isNotEmpty
                ? _stringValue(ref['retrievedAt'])
                : timestamp,
          ),
        );
      }
    }
    collected.sort((a, b) {
      final authorityDelta =
          (b.authorityScore * 1000).round() - (a.authorityScore * 1000).round();
      if (authorityDelta != 0) return authorityDelta;
      final relevanceDelta =
          (b.relevanceScore * 1000).round() - (a.relevanceScore * 1000).round();
      if (relevanceDelta != 0) return relevanceDelta;
      return a.url.compareTo(b.url);
    });
    return collected;
  }

  EvidenceEvaluationResult evaluate({
    required List<EvidenceLedgerEntry> ledger,
    bool evidenceRequired = false,
    bool authorityRequired = false,
    int freshnessHoursMax = 72,
    List<String> requiredDimensions = const <String>[],
    List<String> blockingDimensions = const <String>[],
  }) {
    if (!evidenceRequired) {
      return EvidenceEvaluationResult(
        entries: ledger,
        coverageScore: ledger.isEmpty ? 0 : (ledger.length / 4).clamp(0.0, 1.0),
        authorityScore: ledger.isEmpty
            ? 0
            : ledger
                  .map((item) => item.authorityScore)
                  .reduce((a, b) => a > b ? a : b),
        relevanceScore: ledger.isEmpty
            ? 0
            : ledger
                      .map((item) => item.relevanceScore)
                      .reduce((a, b) => a + b) /
                  ledger.length,
        freshnessHours: ledger.isEmpty
            ? freshnessHoursMax
            : ledger
                  .map((item) => item.freshnessHours)
                  .reduce((a, b) => a < b ? a : b),
        status: 'not_required',
        passed: true,
        authoritySatisfied: true,
        freshnessSatisfied: true,
        evidenceRequired: false,
        coveredDimensions: _nonEmptyUnique(
          ledger.map((item) => item.dimension).toList(growable: false),
        ),
        coveredQueryTaskIds: _nonEmptyUnique(
          ledger.map((item) => item.queryTaskId).toList(growable: false),
        ),
        blockingDimensions: _nonEmptyUnique(blockingDimensions),
        summary: '当前问题不强制依赖外部证据账。',
      );
    }
    if (ledger.isEmpty) {
      return EvidenceEvaluationResult(
        status: 'retry',
        passed: false,
        authoritySatisfied: false,
        freshnessSatisfied: false,
        evidenceRequired: true,
        blockingDimensions: _nonEmptyUnique(blockingDimensions),
        summary: '还没有拿到可用证据。',
      );
    }
    final coverageScore = (ledger.length / 4).clamp(0.0, 1.0).toDouble();
    final authorityScore = ledger
        .map((item) => item.authorityScore)
        .reduce((a, b) => a > b ? a : b);
    final relevanceScore =
        ledger.map((item) => item.relevanceScore).reduce((a, b) => a + b) /
        ledger.length;
    final freshnessHours = ledger
        .map((item) => item.freshnessHours)
        .reduce((a, b) => a < b ? a : b);
    final coveredDimensions = _nonEmptyUnique(
      ledger.map((item) => item.dimension).toList(growable: false),
    );
    final coveredQueryTaskIds = _nonEmptyUnique(
      ledger.map((item) => item.queryTaskId).toList(growable: false),
    );
    final effectiveBlockingDimensions = _nonEmptyUnique(
      blockingDimensions.isNotEmpty ? blockingDimensions : requiredDimensions,
    );
    final missingDimensions = effectiveBlockingDimensions
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty && !coveredDimensions.contains(item))
        .toList(growable: false);
    final authoritySatisfied =
        !authorityRequired ||
        ledger.any(
          (item) =>
              item.sourceTier == 'authority' || item.authorityScore >= 0.8,
        );
    final freshnessSatisfied = freshnessHoursMax <= 0
        ? true
        : ledger.any(
            (item) =>
                item.freshnessHours <= 0 ||
                item.freshnessHours <= freshnessHoursMax,
          );
    final passed =
        authoritySatisfied &&
        freshnessSatisfied &&
        (missingDimensions.isEmpty || coverageScore >= 0.75);
    final canGiveBoundedAnswer =
        ledger.isNotEmpty &&
        (coveredDimensions.isNotEmpty || coverageScore >= 0.35);
    final status = passed
        ? 'full'
        : canGiveBoundedAnswer
        ? 'bounded'
        : 'retry';
    return EvidenceEvaluationResult(
      entries: ledger,
      coverageScore: coverageScore,
      authorityScore: authorityScore,
      relevanceScore: relevanceScore,
      freshnessHours: freshnessHours,
      status: status,
      passed: passed,
      authoritySatisfied: authoritySatisfied,
      freshnessSatisfied: freshnessSatisfied,
      evidenceRequired: true,
      coveredDimensions: coveredDimensions,
      coveredQueryTaskIds: coveredQueryTaskIds,
      blockingDimensions: effectiveBlockingDimensions,
      missingDimensions: missingDimensions,
      summary: status == 'full'
          ? '已收拢 ${ledger.length} 条证据，关键维度已经覆盖。'
          : status == 'bounded'
          ? '已收拢 ${ledger.length} 条证据，可以先回答已确认部分。'
          : '证据还不够稳，需要继续补一轮。',
    );
  }

  List<Map<String, dynamic>> _extractReferences({
    required String toolName,
    required Map<String, dynamic> data,
    required String retrievedAt,
  }) {
    final refs =
        (data['references'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
    if (refs.isNotEmpty) return refs;
    final url = (data['url'] as String?)?.trim() ?? '';
    if (url.isEmpty) return const <Map<String, dynamic>>[];
    return <Map<String, dynamic>>[
      <String, dynamic>{
        'title': (data['title'] as String?)?.trim() ?? url,
        'url': url,
        'snippet': _snippetOfFetchContent(data['content']),
        'source': (data['source'] as String?)?.trim() ?? '',
        'sourceHost': _hostOf(url),
        'sourceTier': toolName == 'web_fetch' ? 'page' : '',
        'retrievedAt': retrievedAt,
        'queryTaskId': _stringValue(data['queryTaskId']),
        'dimension': _stringValue(data['dimension']),
      },
    ];
  }

  String _snippetOfFetchContent(Object? raw) {
    final content = raw?.toString().trim() ?? '';
    if (content.isEmpty) return '';
    if (content.length <= 180) return content;
    return '${content.substring(0, 180)}...';
  }

  String _buildEvidenceId({
    required String domainId,
    required String toolName,
    required String queryTaskId,
    required String url,
  }) {
    final scope = queryTaskId.isNotEmpty ? queryTaskId : toolName;
    return '$domainId::$scope::$url';
  }

  String _resolveSourceTier({
    required String host,
    required List<String> authorityDomains,
  }) {
    if (host.isEmpty) return 'web';
    for (final authority in authorityDomains) {
      if (host == authority || host.endsWith('.$authority')) {
        return 'authority';
      }
    }
    if (host.endsWith('.gov.cn') ||
        host.endsWith('.edu.cn') ||
        host.endsWith('.org.cn')) {
      return 'trusted';
    }
    return 'web';
  }

  double _estimateAuthorityScore({
    required String sourceTier,
    required String host,
    required List<String> authorityDomains,
  }) {
    switch (sourceTier) {
      case 'authority':
        return 1.0;
      case 'trusted':
        return 0.82;
      case 'page':
        return 0.68;
      default:
        for (final authority in authorityDomains) {
          if (host == authority || host.endsWith('.$authority')) return 1.0;
        }
        return 0.45;
    }
  }

  Map<String, dynamic> _buildSlotContributions({
    required SlotStateSnapshot slotState,
    required String title,
    required String url,
    required String snippet,
  }) {
    final combined = '$title $url $snippet'.toLowerCase();
    final contributions = <String, dynamic>{};
    for (final entry in slotState.slotValues.entries) {
      final slot = entry.value;
      final value = slot.value?.toString().trim() ?? '';
      if (value.isEmpty) continue;
      if (combined.contains(value.toLowerCase())) {
        contributions[entry.key] = value;
      }
    }
    return contributions;
  }

  static List<String> _nonEmptyUnique(List<String> values) {
    final seen = <String>{};
    final out = <String>[];
    for (final raw in values) {
      final value = raw.trim();
      if (value.isEmpty || !seen.add(value)) continue;
      out.add(value);
    }
    return out;
  }

  static String _stringValue(Object? value) => value?.toString().trim() ?? '';

  static int? _intValue(Object? value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '');
  }

  static double? _doubleValue(Object? value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  static String _hostOf(String url) =>
      Uri.tryParse(url)?.host.toLowerCase().trim() ?? '';
}
