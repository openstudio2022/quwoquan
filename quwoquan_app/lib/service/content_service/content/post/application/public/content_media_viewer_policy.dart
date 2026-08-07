class ContentMediaViewerFilterOption {
  const ContentMediaViewerFilterOption({
    required this.id,
    required this.labelKey,
    required this.contentType,
  });

  final String id;
  final String labelKey;
  final String? contentType;
}

class ContentMediaViewerPaperThemeOption {
  const ContentMediaViewerPaperThemeOption({
    required this.id,
    required this.labelKey,
  });

  final String id;
  final String labelKey;
}

/// Post-owned read policy consumed by the MediaAsset viewer.
abstract interface class ContentMediaViewerPolicy {
  String get articleDarkPaperDefaultTheme;

  List<ContentMediaViewerPaperThemeOption> get articlePaperThemeOptions;

  List<ContentMediaViewerFilterOption> get workFormatFilters;
}
