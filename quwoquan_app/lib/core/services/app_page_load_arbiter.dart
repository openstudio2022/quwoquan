import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';

enum AppPageLoadPhase { idle, loading, content, empty, failure }

enum AppPageLoadDecisionKind {
  blockingLoading,
  blockingFailure,
  content,
  contentWithNotice,
}

final class AppPageLoadSlice {
  const AppPageLoadSlice({
    required this.id,
    required this.phase,
    this.isCritical = false,
    this.hasUsableContent = false,
    this.semantic,
  });

  final String id;
  final AppPageLoadPhase phase;
  final bool isCritical;
  final bool hasUsableContent;
  final UiErrorSemantic? semantic;
}

final class AppPageLoadDecision {
  const AppPageLoadDecision({
    required this.kind,
    this.semantic,
    this.suppressedSliceIds = const <String>{},
    this.sectionOwnedFailureIds = const <String>{},
  });

  final AppPageLoadDecisionKind kind;
  final UiErrorSemantic? semantic;
  final Set<String> suppressedSliceIds;
  final Set<String> sectionOwnedFailureIds;

  bool suppresses(String sliceId) => suppressedSliceIds.contains(sliceId);
}

/// 页面唯一的等待与错误裁决器。
///
/// 子区块可以继续取数，但只由本裁决结果决定哪个状态可见，避免整页错误、区块
/// 错误和加载动画同时出现。
final class AppPageLoadArbiter {
  const AppPageLoadArbiter._();

  static AppPageLoadDecision decide(Iterable<AppPageLoadSlice> slices) {
    final values = slices.toList(growable: false);
    final criticalWithoutContent = values.where(
      (slice) => slice.isCritical && !slice.hasUsableContent,
    );
    final blockingFailure = criticalWithoutContent
        .where((slice) => slice.phase == AppPageLoadPhase.failure)
        .toList(growable: false);
    if (blockingFailure.isNotEmpty) {
      final selected = _highestPriority(blockingFailure);
      return AppPageLoadDecision(
        kind: AppPageLoadDecisionKind.blockingFailure,
        semantic: selected?.semantic,
        suppressedSliceIds: values
            .where((slice) => slice.id != selected?.id)
            .map((slice) => slice.id)
            .toSet(),
      );
    }
    if (criticalWithoutContent.any(
      (slice) => slice.phase == AppPageLoadPhase.loading,
    )) {
      return AppPageLoadDecision(
        kind: AppPageLoadDecisionKind.blockingLoading,
        suppressedSliceIds: values.map((slice) => slice.id).toSet(),
      );
    }

    final failures = values
        .where(
          (slice) =>
              slice.phase == AppPageLoadPhase.failure && slice.semantic != null,
        )
        .toList(growable: false);
    if (failures.isEmpty) {
      return const AppPageLoadDecision(kind: AppPageLoadDecisionKind.content);
    }

    final criticalFailures = failures
        .where((slice) => slice.isCritical)
        .toList(growable: false);
    if (criticalFailures.isNotEmpty || failures.length >= 2) {
      final selected = _highestPriority(failures);
      return AppPageLoadDecision(
        kind: AppPageLoadDecisionKind.contentWithNotice,
        semantic: selected?.semantic,
        suppressedSliceIds: failures.map((slice) => slice.id).toSet(),
      );
    }

    return AppPageLoadDecision(
      kind: AppPageLoadDecisionKind.content,
      sectionOwnedFailureIds: <String>{failures.single.id},
    );
  }

  static AppPageLoadSlice? _highestPriority(
    Iterable<AppPageLoadSlice> failures,
  ) {
    AppPageLoadSlice? selected;
    var selectedPriority = 1 << 30;
    for (final failure in failures) {
      final group = failure.semantic?.userRecoveryGroup;
      final priority = group == null ? 1 << 29 : _priority(group);
      if (priority < selectedPriority) {
        selected = failure;
        selectedPriority = priority;
      }
    }
    return selected;
  }

  static int _priority(AppUserRecoveryGroup group) {
    return switch (group) {
      AppUserRecoveryGroup.updateApp => 0,
      AppUserRecoveryGroup.loginAgain ||
      AppUserRecoveryGroup.guestSessionUnavailable => 1,
      AppUserRecoveryGroup.enablePermission => 2,
      AppUserRecoveryGroup.connectNetwork => 3,
      AppUserRecoveryGroup.connectionUnavailable => 4,
      AppUserRecoveryGroup.requestTimedOut => 5,
      AppUserRecoveryGroup.serviceUnavailable => 6,
      AppUserRecoveryGroup.invalidContent => 7,
      AppUserRecoveryGroup.waitThenReload => 8,
      AppUserRecoveryGroup.reloadLater => 9,
      AppUserRecoveryGroup.noAccess => 10,
      AppUserRecoveryGroup.contentGone ||
      AppUserRecoveryGroup.contentUnavailable => 11,
    };
  }
}
