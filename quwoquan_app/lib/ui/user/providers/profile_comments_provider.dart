import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';

class ProfileCommentsState {
  final List<CommentDto> comments;
  final String? nextCursor;
  final bool isLoading;
  final bool isLoadingMore;
  final Object? rawError;

  const ProfileCommentsState({
    this.comments = const [],
    this.nextCursor,
    this.isLoading = false,
    this.isLoadingMore = false,
    this.rawError,
  });

  bool get hasMore => nextCursor != null;
  String? get error =>
      rawError == null ? null : runtimeErrorDisplayMessage(rawError!).trim();

  ProfileCommentsState copyWith({
    List<CommentDto>? comments,
    String? Function()? nextCursor,
    bool? isLoading,
    bool? isLoadingMore,
    Object? Function()? rawError,
  }) {
    return ProfileCommentsState(
      comments: comments ?? this.comments,
      nextCursor: nextCursor != null ? nextCursor() : this.nextCursor,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      rawError: rawError != null ? rawError() : this.rawError,
    );
  }
}

class SentCommentsNotifier extends Notifier<ProfileCommentsState> {
  @override
  ProfileCommentsState build() => const ProfileCommentsState();

  Future<void> load() async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, rawError: () => null);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page = await repo.listCommentsByAuthor();
      if (!ref.mounted) return;
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        isLoading: false,
      );
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.isLoadingMore) return;
    state = state.copyWith(isLoadingMore: true);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page = await repo.listCommentsByAuthor(cursor: state.nextCursor);
      if (!ref.mounted) return;
      state = state.copyWith(
        comments: [...state.comments, ...page.items],
        nextCursor: () => page.nextCursor,
        isLoadingMore: false,
      );
    } catch (_) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoadingMore: false);
    }
  }
}

class ReceivedCommentsNotifier extends Notifier<ProfileCommentsState> {
  @override
  ProfileCommentsState build() => const ProfileCommentsState();

  Future<void> load() async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, rawError: () => null);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page = await repo.listCommentsForPostAuthor();
      if (!ref.mounted) return;
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        isLoading: false,
      );
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoading: false, rawError: () => e);
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.isLoadingMore) return;
    state = state.copyWith(isLoadingMore: true);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page = await repo.listCommentsForPostAuthor(
        cursor: state.nextCursor,
      );
      if (!ref.mounted) return;
      state = state.copyWith(
        comments: [...state.comments, ...page.items],
        nextCursor: () => page.nextCursor,
        isLoadingMore: false,
      );
    } catch (_) {
      if (!ref.mounted) return;
      state = state.copyWith(isLoadingMore: false);
    }
  }
}

final sentCommentsProvider =
    NotifierProvider.autoDispose<SentCommentsNotifier, ProfileCommentsState>(
      SentCommentsNotifier.new,
    );

final receivedCommentsProvider =
    NotifierProvider.autoDispose<
      ReceivedCommentsNotifier,
      ProfileCommentsState
    >(ReceivedCommentsNotifier.new);
