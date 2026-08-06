import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/domain/runtime_enums.dart';

/// App presentation surfaces whose optional capabilities have distinct trust
/// boundaries.
enum AssistantPresentationSurfacePolicy { personal, network }

/// Canonical viewport variants understood by immutable Assistant templates.
enum AssistantPresentationViewportClass {
  compact('compact'),
  standard('standard'),
  expanded('expanded');

  const AssistantPresentationViewportClass(this.wireName);

  final String wireName;

  static AssistantPresentationViewportClass fromWidth(
    double width, {
    required double compactBelow,
    required double expandedFrom,
  }) {
    if (!width.isFinite || width <= 0) {
      throw ArgumentError.value(width, 'width', 'must be finite and positive');
    }
    if (!compactBelow.isFinite ||
        !expandedFrom.isFinite ||
        compactBelow <= 0 ||
        expandedFrom <= compactBelow) {
      throw ArgumentError('invalid Assistant presentation breakpoints');
    }
    if (width < compactBelow) {
      return AssistantPresentationViewportClass.compact;
    }
    if (width < expandedFrom) {
      return AssistantPresentationViewportClass.standard;
    }
    return AssistantPresentationViewportClass.expanded;
  }
}

/// Immutable runtime facts used by both the Remote capability advertisement
/// and the Flutter renderer. This type intentionally has no Flutter or cloud
/// transport dependency.
final class AssistantPresentationCapabilitySnapshot {
  factory AssistantPresentationCapabilitySnapshot({
    required AssistantPresentationSurfacePolicy surfacePolicy,
    required AssistantPresentationViewportClass viewportClass,
    required String platform,
    required bool darkTheme,
    required double textScale,
    required bool reducedMotion,
    required bool offline,
    required bool mediaEnabled,
    required bool actionsEnabled,
  }) {
    final normalizedPlatform = platform.trim();
    if (normalizedPlatform.isEmpty) {
      throw ArgumentError.value(platform, 'platform', 'must not be blank');
    }
    if (!textScale.isFinite || textScale <= 0) {
      throw ArgumentError.value(
        textScale,
        'textScale',
        'must be finite and positive',
      );
    }
    return AssistantPresentationCapabilitySnapshot._(
      surfacePolicy: surfacePolicy,
      viewportClass: viewportClass,
      platform: normalizedPlatform,
      darkTheme: darkTheme,
      textScale: textScale,
      reducedMotion: reducedMotion,
      offline: offline,
      mediaEnabled: mediaEnabled,
      actionsEnabled: actionsEnabled,
    );
  }

  const AssistantPresentationCapabilitySnapshot._({
    required this.surfacePolicy,
    required this.viewportClass,
    required this.platform,
    required this.darkTheme,
    required this.textScale,
    required this.reducedMotion,
    required this.offline,
    required this.mediaEnabled,
    required this.actionsEnabled,
  });

  final AssistantPresentationSurfacePolicy surfacePolicy;
  final AssistantPresentationViewportClass viewportClass;
  final String platform;
  final bool darkTheme;
  final double textScale;
  final bool reducedMotion;
  final bool offline;
  final bool mediaEnabled;
  final bool actionsEnabled;

  String get themeWireName => darkTheme ? 'dark' : 'light';

  Set<AssistantPresentationNodeKind> get supportedNodeKinds =>
      AssistantPresentationCapabilityCatalog.supportedNodeKinds(this);

  List<String> get supportedNodeWireNames => List<String>.unmodifiable(
    supportedNodeKinds.map((kind) => kind.wireName),
  );

  List<String> get supportedActionIntents => List<String>.unmodifiable(
    !offline && actionsEnabled
        ? const <String>[
            'Navigate',
            'ApproveTool',
            'ExecuteDeviceAction',
            'ProvideInput',
          ]
        : const <String>[],
  );
}

typedef AssistantPresentationCapabilitySnapshotFactory =
    AssistantPresentationCapabilitySnapshot Function(
      AssistantPresentationSurfacePolicy surfacePolicy,
    );

/// The single node-capability catalog for the App.
///
/// Adding a renderer node changes this catalog once. Remote negotiation and
/// runtime validation both consume the resolved set, so an App can never
/// advertise a node that its renderer does not own.
abstract final class AssistantPresentationCapabilityCatalog {
  static const List<AssistantPresentationNodeKind> _baseNodeKinds =
      <AssistantPresentationNodeKind>[
        AssistantPresentationNodeKind.card,
        AssistantPresentationNodeKind.column,
        AssistantPresentationNodeKind.row,
        AssistantPresentationNodeKind.grid,
        AssistantPresentationNodeKind.list,
        AssistantPresentationNodeKind.carousel,
        AssistantPresentationNodeKind.markdown,
        AssistantPresentationNodeKind.text,
        AssistantPresentationNodeKind.icon,
        AssistantPresentationNodeKind.badge,
        AssistantPresentationNodeKind.divider,
        AssistantPresentationNodeKind.stat,
        AssistantPresentationNodeKind.keyValue,
        AssistantPresentationNodeKind.entityReference,
        AssistantPresentationNodeKind.sourceReference,
        AssistantPresentationNodeKind.timeline,
        AssistantPresentationNodeKind.routeMap,
        AssistantPresentationNodeKind.comparisonTable,
        AssistantPresentationNodeKind.sourceList,
        AssistantPresentationNodeKind.callout,
      ];

  static const List<AssistantPresentationNodeKind> _mediaNodeKinds =
      <AssistantPresentationNodeKind>[
        AssistantPresentationNodeKind.media,
        AssistantPresentationNodeKind.mediaGallery,
      ];

  static const List<AssistantPresentationNodeKind> _actionNodeKinds =
      <AssistantPresentationNodeKind>[
        AssistantPresentationNodeKind.actionGroup,
        AssistantPresentationNodeKind.choiceChips,
        AssistantPresentationNodeKind.dateTimeInput,
        AssistantPresentationNodeKind.confirmationCard,
      ];

  static Set<AssistantPresentationNodeKind> supportedNodeKinds(
    AssistantPresentationCapabilitySnapshot snapshot,
  ) {
    // Global network search currently consumes terminal answer text and owns
    // no semantic renderer or action continuation. Advertising even a base
    // node there would let the server select a document the surface discards.
    if (snapshot.surfacePolicy == AssistantPresentationSurfacePolicy.network) {
      return const <AssistantPresentationNodeKind>{};
    }
    final optionalCapabilitiesAllowed = !snapshot.offline;
    return Set<AssistantPresentationNodeKind>.unmodifiable(
      <AssistantPresentationNodeKind>{
        ..._baseNodeKinds,
        if (optionalCapabilitiesAllowed && snapshot.mediaEnabled)
          ..._mediaNodeKinds,
        if (optionalCapabilitiesAllowed && snapshot.actionsEnabled)
          ..._actionNodeKinds,
      },
    );
  }
}
