/// App-side provenance for a composed search result.
///
/// This is deliberately separate from the Cloud wire contract: local and
/// local-fallback results are produced by the App composition and never cross
/// the transport boundary.
enum SearchResolvedFrom {
  local,
  remote,
  localFallback,
}
