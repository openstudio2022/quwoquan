const String profileInteractionAllFilterKey = 'all';

/// Normalizes the activity projection's filter membership.
///
/// Every activity participates in the aggregate "all" view; authored keys are
/// trimmed, empty keys are discarded, and duplicates collapse deterministically.
List<String> normalizeProfileInteractionFilterKeys(Iterable<String> rawKeys) {
  return <String>{
    profileInteractionAllFilterKey,
    ...rawKeys.map((key) => key.trim()).where((key) => key.isNotEmpty),
  }.toList(growable: false);
}
