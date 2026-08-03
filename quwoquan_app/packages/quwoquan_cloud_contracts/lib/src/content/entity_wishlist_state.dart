/// 当前登录用户对 canonical object 的显式「想去」状态。
final class EntityWishlistState {
  const EntityWishlistState({
    required this.objectId,
    required this.objectKind,
    required this.wishlisted,
  });

  final String objectId;
  final String objectKind;
  final bool wishlisted;
}
