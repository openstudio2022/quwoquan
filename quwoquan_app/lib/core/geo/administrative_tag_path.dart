/// 行政区标签树的根路径。标签树真相源是 `quwoquan_data` 的 taxonomy release，
/// 端侧只负责拼候选路径，是否存在由 tag-service `ResolveTag` 判定。
const String kAdministrativeTagRoot = 'Topic/地理/行政区';

/// 中国四个直辖市。它们在行政区树里直接挂区县，没有中间的地级市层。
const Set<String> _municipalities = <String>{'北京市', '天津市', '上海市', '重庆市'};

/// 省级：省 / 自治区 / 特别行政区 / 直辖市。
final RegExp _provincePattern = RegExp(
  r'^(北京市|天津市|上海市|重庆市|香港特别行政区|澳门特别行政区|.{1,7}?(?:省|自治区))',
);

/// 地级：市 / 自治州 / 地区 / 盟。
final RegExp _prefecturePattern = RegExp(r'^(.{1,9}?(?:市|自治州|地区|盟))');

/// 县级：区 / 县 / 县级市 / 旗 / 林区。
final RegExp _countyPattern = RegExp(r'^(.{1,9}?(?:区|县|市|旗|林区))');

/// 从中文地址串解析行政区链，如 `浙江省杭州市西湖区北山街道1号` → `[浙江省, 杭州市, 西湖区]`。
///
/// 只解析地址开头的连续行政区前缀；街道及更细的门牌不属于行政区，直接丢弃。
/// 直辖市地址（`北京市东城区...`）会跳过地级市层，与标签树形状一致。
///
/// 解析失败返回空列表，调用方据此不产出 `geoTagRef`，不臆造。
List<String> parseChineseAdministrativeChain(String address) {
  var rest = address.trim();
  if (rest.isEmpty) return const <String>[];
  // 部分 provider 会带国名前缀。
  if (rest.startsWith('中国')) {
    rest = rest.substring(2).trimLeft();
  }

  final chain = <String>[];
  final province = _provincePattern.firstMatch(rest)?.group(1);
  if (province == null) return const <String>[];
  chain.add(province);
  rest = rest.substring(province.length);

  if (!_municipalities.contains(province)) {
    final prefecture = _prefecturePattern.firstMatch(rest)?.group(1);
    if (prefecture == null) return chain;
    chain.add(prefecture);
    rest = rest.substring(prefecture.length);
  }

  final county = _countyPattern.firstMatch(rest)?.group(1);
  if (county != null) chain.add(county);
  return chain;
}

/// 由行政区链生成候选 tagRef，从最具体到最粗。
///
/// 调用方按顺序解析，第一个在标签树中存在的即为结果：区县缺失或标签树未覆盖到区县时
/// 自然退化到市级、省级，而不是整体失败。
List<String> administrativeTagRefCandidates(
  List<String> chain, {
  String country = '中国',
}) {
  final normalizedCountry = country.trim();
  if (normalizedCountry.isEmpty) return const <String>[];
  final segments = <String>[
    normalizedCountry,
    ...chain.map((segment) => segment.trim()).where((s) => s.isNotEmpty),
  ];
  final candidates = <String>[];
  for (var depth = segments.length; depth >= 1; depth--) {
    candidates.add(
      '$kAdministrativeTagRoot/${segments.take(depth).join('/')}',
    );
  }
  return candidates;
}

/// 境外一级/二级行政区的本地命名后缀。
///
/// 标签树里的境外一级行政区用当地法定层级命名（日本的都道府县、泰国的府、韩国的道与
/// 广域市），provider 返回的中文地址也沿用同一套后缀，所以按后缀切段就能对上路径。
/// 没有可靠后缀约定的国家（欧美多数国家的中文地址不带层级词）不列在此，只产出国家级
/// 候选——粗粒度的真标签好过按空格瞎切出来的假路径。
final Map<String, List<RegExp>> _overseasSegmentPatterns = <String, List<RegExp>>{
  '日本': <RegExp>[
    RegExp(r'^(.{1,6}?(?:都|道|府|県|县))'),
    RegExp(r'^(.{1,8}?(?:区|市|町|村))'),
  ],
  '韩国': <RegExp>[
    RegExp(r'^(.{1,8}?(?:特别市|广域市|特别自治市|特别自治道|道))'),
    RegExp(r'^(.{1,8}?(?:区|市|郡))'),
  ],
  '泰国': <RegExp>[
    RegExp(r'^(.{1,8}?府)'),
    RegExp(r'^(.{1,8}?(?:市|镇|县))'),
  ],
  '越南': <RegExp>[
    RegExp(r'^(.{1,8}?(?:省|市))'),
    RegExp(r'^(.{1,8}?(?:区|市|县))'),
  ],
};

/// 标签树收录的境外国家。地址里的国名必须逐字命中这里才认，否则宁可不产出 geoTagRef。
///
/// 按最长前缀匹配，避免「中国香港」这类含国名的串被误判成另一个国家。
const List<String> _overseasCountries = <String>[
  '印度尼西亚',
  '乌兹别克斯坦',
  '马来西亚',
  '澳大利亚',
  '阿塞拜疆',
  '格鲁吉亚',
  '马尔代夫',
  '斯里兰卡',
  '柬埔寨',
  '菲律宾',
  '尼泊尔',
  '新加坡',
  '新西兰',
  '阿根廷',
  '摩洛哥',
  '肯尼亚',
  '墨西哥',
  '葡萄牙',
  '西班牙',
  '意大利',
  '奥地利',
  '阿联酋',
  '土耳其',
  '以色列',
  '加拿大',
  '俄罗斯',
  '日本',
  '韩国',
  '泰国',
  '越南',
  '缅甸',
  '老挝',
  '美国',
  '法国',
  '瑞士',
  '德国',
  '英国',
  '捷克',
  '荷兰',
  '希腊',
  '挪威',
  '冰岛',
  '芬兰',
  '瑞典',
  '埃及',
  '南非',
  '秘鲁',
  '智利',
  '巴西',
];

/// 从地址开头识别标签树收录的境外国家，返回国名与其后的剩余串。
({String country, String rest})? _matchOverseasCountry(String address) {
  final trimmed = address.trim();
  String? matched;
  for (final country in _overseasCountries) {
    if (!trimmed.startsWith(country)) continue;
    if (matched == null || country.length > matched.length) matched = country;
  }
  if (matched == null) return null;
  return (
    country: matched,
    rest: trimmed.substring(matched.length).trimLeft(),
  );
}

/// 从境外地址解析行政区链，如 `日本东京都新宿区西新宿2-8-1` → `[东京都, 新宿区]`。
///
/// 返回的链不含国名；国名由 [_matchOverseasCountry] 单独给出。没有后缀约定的国家返回
/// 空链，调用方只拿到国家级候选。
List<String> _parseOverseasChain(String country, String rest) {
  final patterns = _overseasSegmentPatterns[country];
  if (patterns == null) return const <String>[];
  final chain = <String>[];
  var remaining = rest;
  for (final pattern in patterns) {
    final segment = pattern.firstMatch(remaining)?.group(1);
    if (segment == null) break;
    chain.add(segment);
    remaining = remaining.substring(segment.length).trimLeft();
  }
  return chain;
}

/// 由中文地址直接生成候选 tagRef，从最具体到最粗。
///
/// 先按境外国名前缀判定：命中则以该国名为根，否则按中国大陆行政区解析。境外国名优先，
/// 因为境外地址的省市后缀（日本的「県」、泰国的「府」）会被中国规则误吃成省级。
List<String> administrativeTagRefCandidatesFromAddress(String address) {
  final overseas = _matchOverseasCountry(address);
  if (overseas != null) {
    return administrativeTagRefCandidates(
      _parseOverseasChain(overseas.country, overseas.rest),
      country: overseas.country,
    );
  }
  final chain = parseChineseAdministrativeChain(address);
  if (chain.isEmpty) return const <String>[];
  return administrativeTagRefCandidates(chain);
}
