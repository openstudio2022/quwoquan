enum DiscoveryFeedLoadTerminal {
  content,
  canonicalEmpty,
  retainedContent,
  stillBlocked,
  superseded,
  cancelled,
}

/// 一次 Feed generation 的权威终态；Widget 不得在 await 后再读共享状态猜测结果。
final class DiscoveryFeedLoadResult {
  const DiscoveryFeedLoadResult({
    required this.terminal,
    required this.generation,
    this.failure,
  });

  final DiscoveryFeedLoadTerminal terminal;
  final int generation;
  final Object? failure;
}
