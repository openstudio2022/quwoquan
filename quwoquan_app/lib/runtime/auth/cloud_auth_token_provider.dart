abstract class CloudAuthTokenProvider {
  Future<String?> getAccessToken();
}

/// 刻意不出示任何凭证的 null-object 实现。
///
/// 用于媒体数据面等「授权由服务端签发 URL 承载、禁止附加 App bearer」的
/// 传输通道；不是测试替身，生产装配可直接使用。
class UnauthenticatedCloudAuthTokenProvider implements CloudAuthTokenProvider {
  const UnauthenticatedCloudAuthTokenProvider();

  @override
  Future<String?> getAccessToken() async => null;
}
