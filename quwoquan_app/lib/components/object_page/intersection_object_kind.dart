/// 交集对象类型（人/地点事物/圈子/组织），决定头像形状与图标。
///
/// 真相源 = [IntersectionReason.relationKind]（服务端），端不二次推断语义。
enum UnifiedObjectKind {
  person,
  place,
  circle,
  org;

  static UnifiedObjectKind fromRelationKind(String relationKind) {
    switch (relationKind) {
      case 'person':
      case 'user':
        return UnifiedObjectKind.person;
      case 'place':
      case 'poi':
      case 'location':
        return UnifiedObjectKind.place;
      case 'circle':
        return UnifiedObjectKind.circle;
      case 'org':
      case 'organization':
        return UnifiedObjectKind.org;
      default:
        return UnifiedObjectKind.person;
    }
  }
}
