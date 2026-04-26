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
