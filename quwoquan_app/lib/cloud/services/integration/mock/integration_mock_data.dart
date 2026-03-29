class IntegrationMockData {
  const IntegrationMockData._();

  static final List<Map<String, dynamic>> locationPois = <Map<String, dynamic>>[
    <String, dynamic>{
      'id': 'poi_west_lake',
      'name': '西湖风景名胜区',
      'latitude': 30.2431,
      'longitude': 120.1500,
      'address': '杭州市西湖区龙井路1号',
      'distanceMeters': 1200,
    },
    <String, dynamic>{
      'id': 'poi_lingyin',
      'name': '灵隐寺',
      'latitude': 30.2466,
      'longitude': 120.0947,
      'address': '杭州市西湖区法云弄1号',
      'distanceMeters': 3600,
    },
    <String, dynamic>{
      'id': 'poi_longjing',
      'name': '龙井村茶园',
      'latitude': 30.2279,
      'longitude': 120.1162,
      'address': '杭州市西湖区龙井村',
      'distanceMeters': 2100,
    },
    <String, dynamic>{
      'id': 'poi_photo_park',
      'name': '光影摄影公园',
      'latitude': 31.1843,
      'longitude': 121.4456,
      'address': '上海市徐汇区滨江大道',
      'distanceMeters': 880,
    },
  ];
}
