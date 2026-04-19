import 'package:quwoquan_app/assistant/contracts/intent_graph.dart';
import 'package:quwoquan_app/assistant/contracts/query_task_contract.dart';

final RegExp relativeTemporalTokenPattern = RegExp(
  r'(昨天|昨日|明天|后天|今天|周[一二三四五六日天]|上周[一二三四五六日天]|下周[一二三四五六日天]|最近)',
);
final RegExp relativeDayTokenPattern = RegExp(r'(昨天|昨日|明天|后天|今天)');

class TemporalReferenceContext {
  const TemporalReferenceContext({
    required this.referenceNow,
    required this.referenceNowIso,
    required this.timezone,
  });

  final DateTime referenceNow;
  final String referenceNowIso;
  final String timezone;
}

class RelativeTimeResolution {
  const RelativeTimeResolution({
    required this.referenceNow,
    required this.referenceNowIso,
    required this.timezone,
    this.timeScope = '',
    this.timeRangeStart,
    this.timeRangeEnd,
    this.timePoint,
    this.matchedToken = '',
    this.rewrittenQuery = '',
    this.resolvedTemporalHints = const <String>[],
  });

  final DateTime referenceNow;
  final String referenceNowIso;
  final String timezone;
  final String timeScope;
  final DateTime? timeRangeStart;
  final DateTime? timeRangeEnd;
  final DateTime? timePoint;
  final String matchedToken;
  final String rewrittenQuery;
  final List<String> resolvedTemporalHints;

  bool get hasStructuredTime =>
      timeScope.trim().isNotEmpty ||
      timeRangeStart != null ||
      timeRangeEnd != null ||
      timePoint != null;

  String get timeRangeStartIso => timeRangeStart?.toIso8601String() ?? '';

  String get timeRangeEndIso => timeRangeEnd?.toIso8601String() ?? '';

  String get timePointIso =>
      timePoint == null ? '' : _formatIsoDate(timePoint!);
}

enum _WeekdayDirection { past, future, neutral }

class RelativeTimeResolver {
  const RelativeTimeResolver();

  TemporalReferenceContext resolveReferenceContext({
    String referenceNowIso = '',
    String timezone = '',
  }) {
    final parsedNow = DateTime.tryParse(referenceNowIso.trim());
    final referenceNow = parsedNow ?? DateTime.now();
    final effectiveTimezone = timezone.trim().isNotEmpty
        ? timezone.trim()
        : (referenceNow.timeZoneName.trim().isNotEmpty
              ? referenceNow.timeZoneName.trim()
              : 'local');
    return TemporalReferenceContext(
      referenceNow: referenceNow,
      referenceNowIso: referenceNow.toIso8601String(),
      timezone: effectiveTimezone,
    );
  }

  Map<String, dynamic> buildCalendarContext({
    required TemporalReferenceContext reference,
  }) {
    final today = _startOfDay(reference.referenceNow);
    return <String, dynamic>{
      'referenceDate': _formatIsoDate(today),
      'today': <String, dynamic>{
        'date': _formatIsoDate(today),
        'weekday': _weekdayLabel(today.weekday),
      },
      'dayBeforeYesterday': <String, dynamic>{
        'date': _formatIsoDate(today.subtract(const Duration(days: 2))),
        'weekday': _weekdayLabel(
          today.subtract(const Duration(days: 2)).weekday,
        ),
      },
      'yesterday': <String, dynamic>{
        'date': _formatIsoDate(today.subtract(const Duration(days: 1))),
        'weekday': _weekdayLabel(
          today.subtract(const Duration(days: 1)).weekday,
        ),
      },
      'tomorrow': <String, dynamic>{
        'date': _formatIsoDate(today.add(const Duration(days: 1))),
        'weekday': _weekdayLabel(today.add(const Duration(days: 1)).weekday),
      },
      'dayAfterTomorrow': <String, dynamic>{
        'date': _formatIsoDate(today.add(const Duration(days: 2))),
        'weekday': _weekdayLabel(today.add(const Duration(days: 2)).weekday),
      },
      'thisWeek': _buildWeekdayDateMap(today, weekOffset: 0),
      'lastWeek': _buildWeekdayDateMap(today, weekOffset: -1),
      'nextWeek': _buildWeekdayDateMap(today, weekOffset: 1),
    };
  }

  RelativeTimeResolution resolve({
    required String query,
    String referenceNowIso = '',
    String timezone = '',
    String timeScope = '',
    String timeRangeStart = '',
    String timeRangeEnd = '',
    String timePoint = '',
  }) {
    final reference = resolveReferenceContext(
      referenceNowIso: referenceNowIso,
      timezone: timezone,
    );
    final structured = _resolveStructuredRange(
      query: query,
      reference: reference,
      timeScope: timeScope,
      timeRangeStart: timeRangeStart,
      timeRangeEnd: timeRangeEnd,
      timePoint: timePoint,
    );
    if (structured != null) {
      return structured;
    }
    return RelativeTimeResolution(
      referenceNow: reference.referenceNow,
      referenceNowIso: reference.referenceNowIso,
      timezone: reference.timezone,
      rewrittenQuery: query,
    );
  }

  QueryNormalization applyToQueryNormalization({
    required QueryNormalization normalization,
    required String query,
    String referenceNowIso = '',
    String timezone = '',
  }) {
    final effectiveReferenceNowIso = referenceNowIso.trim().isNotEmpty
        ? referenceNowIso.trim()
        : normalization.referenceNowIso.trim();
    final effectiveTimezone = timezone.trim().isNotEmpty
        ? timezone.trim()
        : normalization.timezone.trim();
    final baseQuery = normalization.normalizedQuery.trim().isNotEmpty
        ? normalization.normalizedQuery.trim()
        : query.trim();
    final resolution = resolve(
      query: baseQuery,
      referenceNowIso: effectiveReferenceNowIso,
      timezone: effectiveTimezone,
      timeScope: normalization.timeScope,
      timeRangeStart: normalization.timeRangeStart,
      timeRangeEnd: normalization.timeRangeEnd,
      timePoint: normalization.timePoint,
    );
    final temporalHints = <String>{
      ...normalization.resolvedTemporalHints.map((item) => item.trim()),
      ...resolution.resolvedTemporalHints.map((item) => item.trim()),
    }.where((item) => item.isNotEmpty).toList(growable: false);
    return QueryNormalization(
      normalizedQuery: baseQuery,
      rewrittenQuery: normalization.rewrittenQuery.trim().isNotEmpty
          ? normalization.rewrittenQuery.trim()
          : baseQuery,
      issues: normalization.issues,
      language: normalization.language,
      hints: normalization.hints,
      referenceNowIso: normalization.referenceNowIso.trim().isNotEmpty
          ? normalization.referenceNowIso.trim()
          : resolution.referenceNowIso,
      timezone: normalization.timezone.trim().isNotEmpty
          ? normalization.timezone.trim()
          : resolution.timezone,
      resolvedTemporalHints: temporalHints,
      timeScope: normalization.timeScope.trim().isNotEmpty
          ? normalization.timeScope.trim()
          : resolution.timeScope,
      timeRangeStart: normalization.timeRangeStart.trim().isNotEmpty
          ? normalization.timeRangeStart.trim()
          : resolution.timeRangeStartIso,
      timeRangeEnd: normalization.timeRangeEnd.trim().isNotEmpty
          ? normalization.timeRangeEnd.trim()
          : resolution.timeRangeEndIso,
      timePoint: normalization.timePoint.trim().isNotEmpty
          ? normalization.timePoint.trim()
          : resolution.timePointIso,
    );
  }

  QueryTask applyToQueryTask({
    required QueryTask task,
    required RelativeTimeResolution fallbackResolution,
    String referenceNowIso = '',
    String timezone = '',
  }) {
    final taskResolution = resolve(
      query: task.query.trim().isNotEmpty
          ? task.query.trim()
          : fallbackResolution.rewrittenQuery,
      referenceNowIso: referenceNowIso.trim().isNotEmpty
          ? referenceNowIso.trim()
          : fallbackResolution.referenceNowIso,
      timezone: timezone.trim().isNotEmpty
          ? timezone.trim()
          : (task.timezone.trim().isNotEmpty
                ? task.timezone.trim()
                : fallbackResolution.timezone),
      timeScope: task.timeScope.trim().isNotEmpty
          ? task.timeScope.trim()
          : fallbackResolution.timeScope,
      timeRangeStart: task.timeRangeStart.trim().isNotEmpty
          ? task.timeRangeStart.trim()
          : fallbackResolution.timeRangeStartIso,
      timeRangeEnd: task.timeRangeEnd.trim().isNotEmpty
          ? task.timeRangeEnd.trim()
          : fallbackResolution.timeRangeEndIso,
      timePoint: task.timePoint.trim().isNotEmpty
          ? task.timePoint.trim()
          : fallbackResolution.timePointIso,
    );
    return task.copyWith(
      query: task.query.trim().isNotEmpty
          ? task.query.trim()
          : taskResolution.rewrittenQuery,
      timeScope: task.timeScope.trim().isNotEmpty
          ? task.timeScope.trim()
          : taskResolution.timeScope,
      timeRangeStart: task.timeRangeStart.trim().isNotEmpty
          ? task.timeRangeStart.trim()
          : taskResolution.timeRangeStartIso,
      timeRangeEnd: task.timeRangeEnd.trim().isNotEmpty
          ? task.timeRangeEnd.trim()
          : taskResolution.timeRangeEndIso,
      timePoint: task.timePoint.trim().isNotEmpty
          ? task.timePoint.trim()
          : taskResolution.timePointIso,
      timezone: task.timezone.trim().isNotEmpty
          ? task.timezone.trim()
          : (timezone.isNotEmpty ? timezone : fallbackResolution.timezone),
    );
  }

  IntentGraph applyToIntentGraph({
    required IntentGraph intentGraph,
    required String latestUserQuery,
    String referenceNowIso = '',
    String timezone = '',
  }) {
    final queryNormalization = applyToQueryNormalization(
      normalization: intentGraph.queryNormalization,
      query: intentGraph.queryNormalization.normalizedQuery.trim().isNotEmpty
          ? intentGraph.queryNormalization.normalizedQuery.trim()
          : latestUserQuery.trim(),
      referenceNowIso: referenceNowIso,
      timezone: timezone,
    );
    final fallbackResolution = resolve(
      query: queryNormalization.normalizedQuery.trim().isNotEmpty
          ? queryNormalization.normalizedQuery.trim()
          : latestUserQuery.trim(),
      referenceNowIso: queryNormalization.referenceNowIso,
      timezone: queryNormalization.timezone,
      timeScope: queryNormalization.timeScope,
      timeRangeStart: queryNormalization.timeRangeStart,
      timeRangeEnd: queryNormalization.timeRangeEnd,
      timePoint: queryNormalization.timePoint,
    );
    final queryTasks = intentGraph.queryTasks
        .map(
          (task) => applyToQueryTask(
            task: task,
            fallbackResolution: fallbackResolution,
            referenceNowIso: queryNormalization.referenceNowIso,
            timezone: queryNormalization.timezone,
          ),
        )
        .toList(growable: false);
    return IntentGraph.fromJson(<String, dynamic>{
      ...intentGraph.toJson(),
      'queryNormalization': queryNormalization.toJson(),
      'queryTasks': queryTasks.map((item) => item.toJson()).toList(growable: false),
    });
  }

  RelativeTimeResolution? _resolveStructuredRange({
    required String query,
    required TemporalReferenceContext reference,
    required String timeScope,
    required String timeRangeStart,
    required String timeRangeEnd,
    required String timePoint,
  }) {
    final normalizedScope = timeScope.trim().toLowerCase();
    final parsedPoint = _parseDateToken(timePoint.trim());
    final parsedStart = _parseDateTime(timeRangeStart.trim());
    final parsedEnd = _parseDateTime(timeRangeEnd.trim());
    if (parsedStart != null &&
        parsedEnd != null &&
        !parsedEnd.isBefore(parsedStart)) {
      return _buildResolution(
        query: query,
        reference: reference,
        scope: normalizedScope.isNotEmpty ? normalizedScope : 'custom',
        start: parsedStart,
        end: parsedEnd,
        point: parsedPoint,
      );
    }
    if (parsedPoint != null) {
      final isSameDay = _sameDay(parsedPoint, reference.referenceNow);
      final start = _startOfDay(parsedPoint);
      final end = normalizedScope == 'today' && isSameDay
          ? reference.referenceNow
          : _endOfDay(parsedPoint);
      return _buildResolution(
        query: query,
        reference: reference,
        scope: normalizedScope.isNotEmpty ? normalizedScope : 'year_month_day',
        start: start,
        end: end,
        point: parsedPoint,
      );
    }
    if (normalizedScope == 'today') {
      final point = _startOfDay(reference.referenceNow);
      return _buildResolution(
        query: query,
        reference: reference,
        scope: 'today',
        start: point,
        end: reference.referenceNow,
        point: point,
      );
    }
    return null;
  }

  RelativeTimeResolution? _resolveRelativeDay(
    String query,
    TemporalReferenceContext reference,
  ) {
    const relativeDays = <String, int>{
      '前天': -2,
      '昨天': -1,
      '昨日': -1,
      '昨晚': -1,
      '今天': 0,
      '今日': 0,
      '当天': 0,
      '明天': 1,
      '后天': 2,
    };
    for (final entry in relativeDays.entries) {
      if (!query.contains(entry.key)) {
        continue;
      }
      final point = _startOfDay(
        reference.referenceNow.add(Duration(days: entry.value)),
      );
      final scope = entry.value == 0 ? 'today' : 'year_month_day';
      final end = entry.value == 0 ? reference.referenceNow : _endOfDay(point);
      return _buildResolution(
        query: query,
        reference: reference,
        scope: scope,
        start: point,
        end: end,
        point: point,
        matchedToken: entry.key,
      );
    }
    return null;
  }

  RelativeTimeResolution? _resolveWeekday(
    String query,
    TemporalReferenceContext reference,
  ) {
    final match = RegExp(
      r'((?:上周|下周|本周|这周)?)(周|星期|礼拜)([一二三四五六日天])',
    ).firstMatch(query);
    if (match == null) {
      return null;
    }
    final prefix = (match.group(1) ?? '').trim();
    final weekdayToken = (match.group(3) ?? '').trim();
    final weekday = _weekdayFromToken(weekdayToken);
    if (weekday == null) {
      return null;
    }
    final target = _resolveWeekdayDate(
      referenceDate: _startOfDay(reference.referenceNow),
      query: query,
      prefix: prefix,
      targetWeekday: weekday,
    );
    return _buildResolution(
      query: query,
      reference: reference,
      scope: _sameDay(target, reference.referenceNow)
          ? 'today'
          : 'year_month_day',
      start: target,
      end: _sameDay(target, reference.referenceNow)
          ? reference.referenceNow
          : _endOfDay(target),
      point: target,
      matchedToken: match.group(0)?.trim() ?? '',
    );
  }

  RelativeTimeResolution? _resolveExplicitDate(
    String query,
    TemporalReferenceContext reference,
  ) {
    final match = RegExp(
      r'(20\d{2}[-/年\.]\d{1,2}[-/月\.]\d{1,2}(?:日)?)',
    ).firstMatch(query);
    if (match == null) {
      return null;
    }
    final token = (match.group(0) ?? '').trim();
    final point = _parseDateToken(token);
    if (point == null) {
      return null;
    }
    final start = _startOfDay(point);
    final end = _sameDay(point, reference.referenceNow)
        ? reference.referenceNow
        : _endOfDay(point);
    return _buildResolution(
      query: query,
      reference: reference,
      scope: _sameDay(point, reference.referenceNow)
          ? 'today'
          : 'year_month_day',
      start: start,
      end: end,
      point: start,
      matchedToken: token,
    );
  }

  RelativeTimeResolution _buildResolution({
    required String query,
    required TemporalReferenceContext reference,
    required String scope,
    required DateTime start,
    required DateTime end,
    DateTime? point,
    String matchedToken = '',
  }) {
    final normalizedPoint = point == null ? null : _startOfDay(point);
    final hints = _resolvedTemporalHints(
      matchedToken: matchedToken,
      scope: scope,
      start: start,
      end: end,
      point: normalizedPoint,
    );
    return RelativeTimeResolution(
      referenceNow: reference.referenceNow,
      referenceNowIso: reference.referenceNowIso,
      timezone: reference.timezone,
      timeScope: scope,
      timeRangeStart: start,
      timeRangeEnd: end,
      timePoint: normalizedPoint,
      matchedToken: matchedToken,
      rewrittenQuery: _rewriteQuery(
        query,
        RelativeTimeResolution(
          referenceNow: reference.referenceNow,
          referenceNowIso: reference.referenceNowIso,
          timezone: reference.timezone,
          timeScope: scope,
          timeRangeStart: start,
          timeRangeEnd: end,
          timePoint: normalizedPoint,
          matchedToken: matchedToken,
          resolvedTemporalHints: hints,
        ),
      ),
      resolvedTemporalHints: hints,
    );
  }

  DateTime _resolveWeekdayDate({
    required DateTime referenceDate,
    required String query,
    required String prefix,
    required int targetWeekday,
  }) {
    final weekStart = _startOfWeek(referenceDate);
    if (prefix == '上周') {
      return weekStart.subtract(Duration(days: 7 - (targetWeekday - 1)));
    }
    if (prefix == '下周') {
      return weekStart.add(Duration(days: 7 + (targetWeekday - 1)));
    }
    if (prefix == '本周' || prefix == '这周') {
      return weekStart.add(Duration(days: targetWeekday - 1));
    }
    final thisWeekTarget = weekStart.add(Duration(days: targetWeekday - 1));
    switch (_weekdayDirection(query)) {
      case _WeekdayDirection.past:
        return thisWeekTarget.isAfter(referenceDate)
            ? thisWeekTarget.subtract(const Duration(days: 7))
            : thisWeekTarget;
      case _WeekdayDirection.future:
        return thisWeekTarget.isBefore(referenceDate)
            ? thisWeekTarget.add(const Duration(days: 7))
            : thisWeekTarget;
      case _WeekdayDirection.neutral:
        if (_sameDay(thisWeekTarget, referenceDate)) {
          return thisWeekTarget;
        }
        final delta = thisWeekTarget.difference(referenceDate).inDays;
        if (delta.abs() <= 3) {
          return thisWeekTarget;
        }
        return delta < 0
            ? thisWeekTarget.add(const Duration(days: 7))
            : thisWeekTarget;
    }
  }

  _WeekdayDirection _weekdayDirection(String query) {
    if (RegExp(r'(为什么|为何|原因|复盘|回顾|发生了什么|发生什么|怎么了|怎么样了)').hasMatch(query)) {
      return _WeekdayDirection.past;
    }
    if (RegExp(r'(会不会|会怎样|将会|预报|预测|预计|适合|要不要)').hasMatch(query)) {
      return _WeekdayDirection.future;
    }
    return _WeekdayDirection.neutral;
  }

  int? _weekdayFromToken(String token) {
    switch (token) {
      case '一':
        return DateTime.monday;
      case '二':
        return DateTime.tuesday;
      case '三':
        return DateTime.wednesday;
      case '四':
        return DateTime.thursday;
      case '五':
        return DateTime.friday;
      case '六':
        return DateTime.saturday;
      case '日':
      case '天':
        return DateTime.sunday;
      default:
        return null;
    }
  }

  List<String> _resolvedTemporalHints({
    required String matchedToken,
    required String scope,
    required DateTime start,
    required DateTime end,
    required DateTime? point,
  }) {
    final hints = <String>[];
    if (matchedToken.isNotEmpty && point != null) {
      hints.add('$matchedToken -> ${_formatIsoDate(point)}');
    } else if (matchedToken.isNotEmpty) {
      hints.add(
        '$matchedToken -> ${_formatIsoDate(start)}..${_formatIsoDate(end)}',
      );
    }
    if (scope.trim().isNotEmpty) {
      hints.add('scope:$scope');
    }
    return hints;
  }

  String _rewriteQuery(String query, RelativeTimeResolution resolution) {
    final base = _compressWhitespace(query);
    if (!resolution.hasStructuredTime) {
      return base;
    }
    final replacement = resolution.timePoint != null
        ? _formatIsoDate(resolution.timePoint!)
        : '时间范围:${_formatIsoDate(resolution.timeRangeStart!)}..${_formatIsoDate(resolution.timeRangeEnd!)}';
    final rewritten =
        resolution.matchedToken.isNotEmpty &&
            base.contains(resolution.matchedToken)
        ? base.replaceFirst(resolution.matchedToken, replacement)
        : base;
    final hints = <String>[
      if (resolution.timePoint != null) _formatIsoDate(resolution.timePoint!),
      if (resolution.timePoint == null &&
          resolution.timeRangeStart != null &&
          resolution.timeRangeEnd != null)
        '时间范围:${_formatIsoDate(resolution.timeRangeStart!)}..${_formatIsoDate(resolution.timeRangeEnd!)}',
    ];
    return _appendDistinctHints(rewritten, hints);
  }

  String _appendDistinctHints(String query, List<String> hints) {
    final base = _compressWhitespace(query);
    if (base.isEmpty) {
      return hints
          .map((item) => item.trim())
          .where((item) => item.isNotEmpty)
          .join(' ');
    }
    final existing = _normalizedToken(base);
    final additions = hints
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty)
        .where((item) => !existing.contains(_normalizedToken(item)))
        .toList(growable: false);
    if (additions.isEmpty) {
      return base;
    }
    return '$base ${additions.join(' ')}'.trim();
  }

  String _normalizedToken(String raw) {
    return raw.replaceAll(RegExp(r'[\s:：|｜/、,，。！？!?._-]+'), '').toLowerCase();
  }

  DateTime? _parseDateToken(String raw) {
    final text = raw.trim();
    if (text.isEmpty) {
      return null;
    }
    final match = RegExp(
      r'(20\d{2})[-/年\.](\d{1,2})[-/月\.](\d{1,2})',
    ).firstMatch(text);
    if (match == null) {
      return null;
    }
    final year = int.tryParse(match.group(1) ?? '');
    final month = int.tryParse(match.group(2) ?? '');
    final day = int.tryParse(match.group(3) ?? '');
    if (year == null || month == null || day == null) {
      return null;
    }
    final date = DateTime(year, month, day);
    if (date.year != year || date.month != month || date.day != day) {
      return null;
    }
    return date;
  }

  DateTime? _parseDateTime(String raw) {
    final text = raw.trim();
    if (text.isEmpty) {
      return null;
    }
    return DateTime.tryParse(text) ?? _parseDateToken(text);
  }

  DateTime _startOfWeek(DateTime date) {
    final day = _startOfDay(date);
    return day.subtract(Duration(days: day.weekday - 1));
  }

  Map<String, String> _buildWeekdayDateMap(
    DateTime referenceDate, {
    required int weekOffset,
  }) {
    final start = _startOfWeek(
      referenceDate,
    ).add(Duration(days: weekOffset * 7));
    return <String, String>{
      for (var index = 0; index < 7; index += 1)
        _weekdayLabel(start.add(Duration(days: index)).weekday): _formatIsoDate(
          start.add(Duration(days: index)),
        ),
    };
  }

  DateTime _startOfDay(DateTime date) {
    return DateTime(date.year, date.month, date.day);
  }

  DateTime _endOfDay(DateTime date) {
    return DateTime(date.year, date.month, date.day, 23, 59, 59, 999);
  }

  bool _sameDay(DateTime a, DateTime b) {
    return a.year == b.year && a.month == b.month && a.day == b.day;
  }

  String _compressWhitespace(String raw) {
    return raw.trim().replaceAll(RegExp(r'\s+'), ' ');
  }

  String _weekdayLabel(int weekday) {
    switch (weekday) {
      case DateTime.monday:
        return '周一';
      case DateTime.tuesday:
        return '周二';
      case DateTime.wednesday:
        return '周三';
      case DateTime.thursday:
        return '周四';
      case DateTime.friday:
        return '周五';
      case DateTime.saturday:
        return '周六';
      case DateTime.sunday:
        return '周日';
      default:
        return '';
    }
  }
}

String _formatIsoDate(DateTime date) {
  final y = date.year.toString().padLeft(4, '0');
  final m = date.month.toString().padLeft(2, '0');
  final d = date.day.toString().padLeft(2, '0');
  return '$y-$m-$d';
}
