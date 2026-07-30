import 'dart:math' as math;

/// 太阳高度角（度）。地平线为 0，天顶为 90，地平线以下为负。
///
/// 实现按 NOAA 的低精度太阳位置算法：对判定「蓝调 / 金色 / 白天 / 夜间」这种以度为
/// 单位的窗口足够（误差约 0.01°），比查日出日落时刻表省掉一次网络往返，也不需要把
/// 时区数据打进包——`capturedAt` 已经带偏移，经纬度来自 EXIF。
///
/// 不做大气折射与海拔修正：这两项影响在 0.5° 量级，只会让紧贴窗口边界的照片落到相邻
/// 窗口，而窗口本身就是模糊的产品口径，不是物理事实。
double solarElevationDegrees({
  required DateTime capturedAt,
  required double latitude,
  required double longitude,
}) {
  final utc = capturedAt.toUtc();
  final julianDay = _julianDay(utc);
  // 儒略世纪，J2000.0 起算。
  final t = (julianDay - 2451545.0) / 36525.0;

  final geomMeanLongSun = _wrap360(280.46646 + t * (36000.76983 + t * 0.0003032));
  final geomMeanAnomalySun = 357.52911 + t * (35999.05029 - 0.0001537 * t);
  final eccentricity = 0.016708634 - t * (0.000042037 + 0.0000001267 * t);

  final anomalyRad = _radians(geomMeanAnomalySun);
  final equationOfCenter =
      math.sin(anomalyRad) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
      math.sin(2 * anomalyRad) * (0.019993 - 0.000101 * t) +
      math.sin(3 * anomalyRad) * 0.000289;

  final trueLongitude = geomMeanLongSun + equationOfCenter;
  final apparentLongitude =
      trueLongitude -
      0.00569 -
      0.00478 * math.sin(_radians(125.04 - 1934.136 * t));

  final meanObliquity =
      23.0 +
      (26.0 +
              ((21.448 -
                      t * (46.815 + t * (0.00059 - t * 0.001813))) /
                  60.0)) /
          60.0;
  final obliquity =
      meanObliquity + 0.00256 * math.cos(_radians(125.04 - 1934.136 * t));

  final declination = _degrees(
    math.asin(
      math.sin(_radians(obliquity)) * math.sin(_radians(apparentLongitude)),
    ),
  );

  final varY = math.tan(_radians(obliquity / 2)) *
      math.tan(_radians(obliquity / 2));
  final equationOfTime = 4 *
      _degrees(
        varY * math.sin(2 * _radians(geomMeanLongSun)) -
            2 * eccentricity * math.sin(anomalyRad) +
            4 *
                eccentricity *
                varY *
                math.sin(anomalyRad) *
                math.cos(2 * _radians(geomMeanLongSun)) -
            0.5 * varY * varY * math.sin(4 * _radians(geomMeanLongSun)) -
            1.25 *
                eccentricity *
                eccentricity *
                math.sin(2 * anomalyRad),
      );

  final minutesUtc =
      utc.hour * 60 + utc.minute + utc.second / 60 + utc.millisecond / 60000;
  // 真太阳时（分钟），4 分钟/经度。
  final trueSolarTime = _wrapPositive(
    minutesUtc + equationOfTime + 4 * longitude,
    1440,
  );
  final hourAngle = trueSolarTime / 4 < 0
      ? trueSolarTime / 4 + 180
      : trueSolarTime / 4 - 180;

  final latRad = _radians(latitude);
  final decRad = _radians(declination);
  final zenith = _degrees(
    math.acos(
      (math.sin(latRad) * math.sin(decRad) +
              math.cos(latRad) *
                  math.cos(decRad) *
                  math.cos(_radians(hourAngle)))
          .clamp(-1.0, 1.0),
    ),
  );
  return 90.0 - zenith;
}

double _julianDay(DateTime utc) {
  var year = utc.year;
  var month = utc.month;
  if (month <= 2) {
    year -= 1;
    month += 12;
  }
  final a = (year / 100).floor();
  final b = 2 - a + (a / 4).floor();
  final dayFraction =
      (utc.hour + utc.minute / 60 + utc.second / 3600) / 24.0;
  return (365.25 * (year + 4716)).floor() +
      (30.6001 * (month + 1)).floor() +
      utc.day +
      dayFraction +
      b -
      1524.5;
}

double _radians(double degrees) => degrees * math.pi / 180.0;

double _degrees(double radians) => radians * 180.0 / math.pi;

double _wrap360(double value) => _wrapPositive(value, 360);

double _wrapPositive(double value, double period) {
  final remainder = value % period;
  return remainder < 0 ? remainder + period : remainder;
}
