typedef WorksViewerAction = void Function();
typedef WorksViewerActionIdSink = void Function(String actionId);
typedef WorksViewerStringSetSink = void Function(Set<String> values);

final class WorksViewerShareResult {
  const WorksViewerShareResult({required this.actionId, required this.success});

  final String actionId;
  final bool success;
}

final class WorksViewerMoreActionOption {
  const WorksViewerMoreActionOption({required this.id, required this.label});

  final String id;
  final String label;
}

/// Media-owned input contract consumed by the Post more-action presentation.
final class WorksViewerMoreActionsConfig {
  const WorksViewerMoreActionsConfig({
    this.showShareAction = false,
    this.showViewOriginalAction = false,
    this.onCopyLink,
    this.onViewOriginal,
    this.onThemeToggle,
    this.onNotInterested,
    this.onBlockUser,
    this.onBlockWords,
    this.onReport,
    this.onShare,
    this.showDeleteAction = false,
    this.onDelete,
    this.onActionInvoked,
    this.filterOptions = const <WorksViewerMoreActionOption>[],
    this.selectedFilterIds = const <String>[],
    this.onFilterSelectionChanged,
    this.readingOptions = const <WorksViewerMoreActionOption>[],
    this.selectedReadingOptionId,
    this.onReadingOptionChanged,
    this.forceDarkAppearance = false,
  });

  final bool showShareAction;
  final bool showViewOriginalAction;
  final WorksViewerAction? onCopyLink;
  final WorksViewerAction? onViewOriginal;
  final WorksViewerAction? onThemeToggle;
  final WorksViewerAction? onNotInterested;
  final WorksViewerAction? onBlockUser;
  final WorksViewerAction? onBlockWords;
  final WorksViewerAction? onReport;
  final WorksViewerAction? onShare;
  final bool showDeleteAction;
  final WorksViewerAction? onDelete;
  final WorksViewerActionIdSink? onActionInvoked;
  final List<WorksViewerMoreActionOption> filterOptions;
  final List<String> selectedFilterIds;
  final WorksViewerStringSetSink? onFilterSelectionChanged;
  final List<WorksViewerMoreActionOption> readingOptions;
  final String? selectedReadingOptionId;
  final WorksViewerActionIdSink? onReadingOptionChanged;
  final bool forceDarkAppearance;
}
