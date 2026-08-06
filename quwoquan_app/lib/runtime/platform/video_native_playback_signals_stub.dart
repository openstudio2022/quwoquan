/// Non-Android platforms do not emit native settle evidence.
Map<String, String> videoNativePlaybackSignalRequestHeadersImpl(
  String sessionToken,
) {
  return const <String, String>{};
}

Stream<Object> videoNativePlaybackSignalsForTokenImpl(String sessionToken) {
  return const Stream<Object>.empty();
}
