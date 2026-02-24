class CursorPage<T> {
  const CursorPage({
    required this.items,
    this.nextCursor,
  });

  final List<T> items;
  final String? nextCursor;
}
