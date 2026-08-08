/// Canonical ContactHome query filter.
///
/// Presentation labels are deliberately excluded: localized copy must never
/// become an API query or cache identity.
enum ChatContactHomeFilter {
  all('all'),
  mutual('mutual'),
  circle('circle'),
  group('group');

  const ChatContactHomeFilter(this.wireValue);

  final String wireValue;
}
