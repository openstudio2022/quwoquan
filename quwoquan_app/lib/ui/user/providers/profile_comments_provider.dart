import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

class ProfileCommentsState {
  final List<CommentDto> comments;
  final String? nextCursor;
  final bool isLoading;
  final bool isLoadingMore;
  final String? error;

  const ProfileCommentsState({
    this.comments = const [],
    this.nextCursor,
    this.isLoading = false,
    this.isLoadingMore = false,
    this.error,
  });

  bool get hasMore => nextCursor != null;

  ProfileCommentsState copyWith({
    List<CommentDto>? comments,
    String? Function()? nextCursor,
    bool? isLoading,
    bool? isLoadingMore,
    String? Function()? error,
  }) {
    return ProfileCommentsState(
      comments: comments ?? this.comments,
      nextCursor: nextCursor != null ? nextCursor() : this.nextCursor,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      error: error != null ? error() : this.error,
    );
  }
}

class SentCommentsNotifier extends Notifier<ProfileCommentsState> {
  @override
  ProfileCommentsState build() => const ProfileCommentsState();

  Future<void> load() async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, error: () => null);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page = await repo.listCommentsByAuthor();
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: () => e.toString());
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.isLoadingMore) return;
    state = state.copyWith(isLoadingMore: true);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page =
          await repo.listCommentsByAuthor(cursor: state.nextCursor);
      state = state.copyWith(
        comments: [...state.comments, ...page.items],
        nextCursor: () => page.nextCursor,
        isLoadingMore: false,
      );
    } catch (_) {
      state = state.copyWith(isLoadingMore: false);
    }
  }
}

class ReceivedCommentsNotifier extends Notifier<ProfileCommentsState> {
  @override
  ProfileCommentsState build() => const ProfileCommentsState();

  Future<void> load() async {
    if (state.isLoading) return;
    state = state.copyWith(isLoading: true, error: () => null);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page = await repo.listCommentsForPostAuthor();
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        isLoading: false,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, error: () => e.toString());
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.isLoadingMore) return;
    state = state.copyWith(isLoadingMore: true);
    final repo = ref.read(contentRepositoryProvider);
    try {
      final page =
          await repo.listCommentsForPostAuthor(cursor: state.nextCursor);
      state = state.copyWith(
        comments: [...state.comments, ...page.items],
        nextCursor: () => page.nextCursor,
        isLoadingMore: false,
      );
    } catch (_) {
      state = state.copyWith(isLoadingMore: false);
    }
  }
}

final sentCommentsProvider =
    NotifierProvider.autoDispose<SentCommentsNotifier, ProfileCommentsState>(
  SentCommentsNotifier.new,
);

final receivedCommentsProvider =
    NotifierProvider.autoDispose<ReceivedCommentsNotifier, ProfileCommentsState>(
  ReceivedCommentsNotifier.new,
);
