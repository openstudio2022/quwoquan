import 'package:quwoquan_app/service/search_service/search/search_index_view/presentation/search_suggestion_models.dart';

class SearchInspirationChipView {
  const SearchInspirationChipView({
    required this.title,
    required this.subtitle,
    this.query,
  });

  final String title;
  final String subtitle;
  final String? query;
}

class SearchInspirationCardView {
  const SearchInspirationCardView({
    required this.id,
    required this.title,
    required this.subtitle,
    this.coverUrl,
    this.query,
  });

  final String id;
  final String title;
  final String subtitle;
  final String? coverUrl;
  final String? query;
}

class SearchInspirationPersonView {
  const SearchInspirationPersonView({
    required this.id,
    required this.displayName,
    required this.headline,
    required this.reason,
    this.avatarUrl,
  });

  final String id;
  final String displayName;
  final String headline;
  final String reason;
  final String? avatarUrl;
}

class SearchInspirationState {
  const SearchInspirationState({
    this.todayIntersections = const <SearchInspirationChipView>[],
    this.guessKeywords = const <NetworkSearchSuggestion>[],
    this.guessBatchIndex = 0,
    this.discoverCircles = const <SearchInspirationCardView>[],
    this.discoverLocations = const <SearchInspirationCardView>[],
    this.people = const <SearchInspirationPersonView>[],
    this.isLoading = false,
  });

  final List<SearchInspirationChipView> todayIntersections;
  final List<NetworkSearchSuggestion> guessKeywords;
  final int guessBatchIndex;
  final List<SearchInspirationCardView> discoverCircles;
  final List<SearchInspirationCardView> discoverLocations;
  final List<SearchInspirationPersonView> people;
  final bool isLoading;

  bool get isEmpty =>
      todayIntersections.isEmpty &&
      guessKeywords.isEmpty &&
      discoverCircles.isEmpty &&
      discoverLocations.isEmpty &&
      people.isEmpty;

  SearchInspirationState copyWith({
    List<SearchInspirationChipView>? todayIntersections,
    List<NetworkSearchSuggestion>? guessKeywords,
    int? guessBatchIndex,
    List<SearchInspirationCardView>? discoverCircles,
    List<SearchInspirationCardView>? discoverLocations,
    List<SearchInspirationPersonView>? people,
    bool? isLoading,
  }) {
    return SearchInspirationState(
      todayIntersections: todayIntersections ?? this.todayIntersections,
      guessKeywords: guessKeywords ?? this.guessKeywords,
      guessBatchIndex: guessBatchIndex ?? this.guessBatchIndex,
      discoverCircles: discoverCircles ?? this.discoverCircles,
      discoverLocations: discoverLocations ?? this.discoverLocations,
      people: people ?? this.people,
      isLoading: isLoading ?? this.isLoading,
    );
  }
}
