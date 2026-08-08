part of 'home_multi_form_feed.dart';

/// Tracks mounted feed entries so scroll restoration can resolve stable IDs.
class _HomeFeedAnchorMarkerRegistry {
  final Map<String, _RenderHomeFeedAnchorMarker> _markers =
      <String, _RenderHomeFeedAnchorMarker>{};

  _RenderHomeFeedAnchorMarker? operator [](String stableEntryIdentity) {
    return _markers[stableEntryIdentity];
  }

  Iterable<_RenderHomeFeedAnchorMarker> get mountedMarkers => _markers.values;

  void attach(_RenderHomeFeedAnchorMarker marker) {
    _markers[marker.stableEntryIdentity] = marker;
  }

  void detach(_RenderHomeFeedAnchorMarker marker) {
    if (identical(_markers[marker.stableEntryIdentity], marker)) {
      _markers.remove(marker.stableEntryIdentity);
    }
  }
}

class _HomeFeedAnchorMarker extends SingleChildRenderObjectWidget {
  const _HomeFeedAnchorMarker({
    super.key,
    required this.registry,
    required this.stableEntryIdentity,
    required this.entryIndex,
    required super.child,
  });

  final _HomeFeedAnchorMarkerRegistry registry;
  final String stableEntryIdentity;
  final int entryIndex;

  @override
  _RenderHomeFeedAnchorMarker createRenderObject(BuildContext context) {
    return _RenderHomeFeedAnchorMarker(
      registry: registry,
      stableEntryIdentity: stableEntryIdentity,
      entryIndex: entryIndex,
    );
  }

  @override
  void updateRenderObject(
    BuildContext context,
    _RenderHomeFeedAnchorMarker renderObject,
  ) {
    renderObject
      ..registry = registry
      ..stableEntryIdentity = stableEntryIdentity
      ..entryIndex = entryIndex;
  }
}

class _RenderHomeFeedAnchorMarker extends RenderProxyBox {
  _RenderHomeFeedAnchorMarker({
    required this._registry,
    required this._stableEntryIdentity,
    required this.entryIndex,
  });

  _HomeFeedAnchorMarkerRegistry _registry;
  String _stableEntryIdentity;
  int entryIndex;

  _HomeFeedAnchorMarkerRegistry get registry => _registry;
  set registry(_HomeFeedAnchorMarkerRegistry value) {
    if (identical(value, _registry)) {
      return;
    }
    if (attached) {
      _registry.detach(this);
    }
    _registry = value;
    if (attached) {
      _registry.attach(this);
    }
  }

  String get stableEntryIdentity => _stableEntryIdentity;
  set stableEntryIdentity(String value) {
    if (value == _stableEntryIdentity) {
      return;
    }
    if (attached) {
      _registry.detach(this);
    }
    _stableEntryIdentity = value;
    if (attached) {
      _registry.attach(this);
    }
  }

  @override
  void attach(PipelineOwner owner) {
    super.attach(owner);
    _registry.attach(this);
  }

  @override
  void detach() {
    _registry.detach(this);
    super.detach();
  }

  ({double top, double height})? geometryInViewport(
    RenderBox ancestor, {
    required double scrollOffset,
  }) {
    if (!attached || !hasSize || !ancestor.attached || !ancestor.hasSize) {
      return null;
    }
    final viewport = RenderAbstractViewport.maybeOf(this);
    if (viewport == null) {
      return null;
    }
    final itemScrollOffset = viewport.getOffsetToReveal(this, 0).offset;
    if (!itemScrollOffset.isFinite) {
      return null;
    }
    // 可见性由调用方以 reveal offset 与真实 viewport 高度裁剪。不能沿
    // RenderObject.parent 寻找 [ancestor] 来判断 offstage：ScrollView 中间的
    // viewport/semantics 组合并不保证该人工遍历能命中外层 RenderBox，会把
    // 所有真实挂载的 sliver child 错判为不可见，导致频道卸载时完全没有锚点。
    final top = itemScrollOffset - scrollOffset;
    return (top: top, height: size.height);
  }
}

class _HomeFeedAnchorCandidate {
  const _HomeFeedAnchorCandidate({
    required this.marker,
    required this.viewportOffset,
  });

  final _RenderHomeFeedAnchorMarker marker;
  final double viewportOffset;

  bool isPreferredTo(_HomeFeedAnchorCandidate other) {
    final isPost = marker.stableEntryIdentity.startsWith('post:');
    final otherIsPost = other.marker.stableEntryIdentity.startsWith('post:');
    if (isPost != otherIsPost) {
      return isPost;
    }
    final overlapsTop = viewportOffset <= AppSpacing.zero;
    final otherOverlapsTop = other.viewportOffset <= AppSpacing.zero;
    if (overlapsTop != otherOverlapsTop) {
      return overlapsTop;
    }
    final distance = viewportOffset.abs();
    final otherDistance = other.viewportOffset.abs();
    if (distance != otherDistance) {
      return distance < otherDistance;
    }
    return marker.entryIndex < other.marker.entryIndex;
  }
}

class _HomeFeedMountedAnchorGeometry {
  const _HomeFeedMountedAnchorGeometry({
    required this.marker,
    required this.itemScrollOffset,
    required this.height,
  });

  final _RenderHomeFeedAnchorMarker marker;
  final double itemScrollOffset;
  final double height;
}
