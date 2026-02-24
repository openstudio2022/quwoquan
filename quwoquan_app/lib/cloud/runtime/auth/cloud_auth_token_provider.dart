abstract class CloudAuthTokenProvider {
  Future<String?> getAccessToken();
}

class StubCloudAuthTokenProvider implements CloudAuthTokenProvider {
  const StubCloudAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => null;
}
