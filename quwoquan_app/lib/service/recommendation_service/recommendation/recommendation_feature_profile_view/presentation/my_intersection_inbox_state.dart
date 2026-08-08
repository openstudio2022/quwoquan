import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class MyIntersectionSummaryState {
  const MyIntersectionSummaryState({
    this.summary,
    this.isLoading = false,
    this.rawError,
  });

  final IntersectionInboxSummary? summary;
  final bool isLoading;
  final Object? rawError;

  bool get hasNew => (summary?.totalNewCount ?? 0) > 0;
  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  MyIntersectionSummaryState copyWith({
    IntersectionInboxSummary? summary,
    bool? isLoading,
    Object? Function()? rawError,
  }) {
    return MyIntersectionSummaryState(
      summary: summary ?? this.summary,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}

class MyIntersectionPreviewState {
  const MyIntersectionPreviewState({
    this.items = const <IntersectionReason>[],
    this.isLoading = false,
    this.rawError,
  });

  final List<IntersectionReason> items;
  final bool isLoading;
  final Object? rawError;

  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  MyIntersectionPreviewState copyWith({
    List<IntersectionReason>? items,
    bool? isLoading,
    Object? Function()? rawError,
  }) {
    return MyIntersectionPreviewState(
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}

class MyIntersectionListState {
  const MyIntersectionListState({
    this.dimension = '',
    this.filter = '',
    this.sourceRef = '',
    this.timeBucket = '',
    this.items = const <IntersectionReason>[],
    this.isLoading = false,
    this.rawError,
  });

  final String dimension;
  final String filter;
  final String sourceRef;
  final String timeBucket;
  final List<IntersectionReason> items;
  final bool isLoading;
  final Object? rawError;

  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  MyIntersectionListState copyWith({
    String? dimension,
    String? filter,
    String? sourceRef,
    String? timeBucket,
    List<IntersectionReason>? items,
    bool? isLoading,
    Object? Function()? rawError,
  }) {
    return MyIntersectionListState(
      dimension: dimension ?? this.dimension,
      filter: filter ?? this.filter,
      sourceRef: sourceRef ?? this.sourceRef,
      timeBucket: timeBucket ?? this.timeBucket,
      items: items ?? this.items,
      isLoading: isLoading ?? this.isLoading,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}
