/// 交集对象类型闭集（人/圈/校/地/企），决定头像形状、图标与统一品牌蓝角标文字。
///
/// 真相源 = [IntersectionReason.objectKind]（云侧闭集 person|circle|school|place|enterprise）；
/// objectKind 缺省时回退 relationKind 旧词，端不二次推断语义。
enum UnifiedObjectKind {
  person,
  circle,
  school,
  place,
  enterprise;

  static UnifiedObjectKind resolve({
    String objectKind = '',
    String relationKind = '',
  }) {
    switch (objectKind.trim()) {
      case 'person':
        return UnifiedObjectKind.person;
      case 'circle':
        return UnifiedObjectKind.circle;
      case 'school':
        return UnifiedObjectKind.school;
      case 'place':
        return UnifiedObjectKind.place;
      case 'enterprise':
        return UnifiedObjectKind.enterprise;
    }
    switch (relationKind.trim()) {
      case 'person':
      case 'user':
        return UnifiedObjectKind.person;
      case 'place':
      case 'poi':
      case 'location':
        return UnifiedObjectKind.place;
      case 'circle':
        return UnifiedObjectKind.circle;
      case 'school':
      case 'university':
        return UnifiedObjectKind.school;
      case 'org':
      case 'organization':
      case 'enterprise':
      case 'brand':
        return UnifiedObjectKind.enterprise;
      default:
        return UnifiedObjectKind.person;
    }
  }
}
