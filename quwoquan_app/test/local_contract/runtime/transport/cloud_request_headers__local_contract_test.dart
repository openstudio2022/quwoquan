import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/cloud_request_headers.dart';

final class _HeaderClientContext implements CloudClientContextProvider {
  const _HeaderClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'header-session',
      platform: 'android',
      appVersion: '1.9.0',
      appBuild: '19000',
      locale: 'zh-CN',
      deviceActorId: 'trusted-after-token-only',
      regionCode: '440000',
      carrier: 'chinatelecom',
    );
  }
}

void main() {
  tearDown(() {
    CloudClientContextRegistry.configure(
      const FallbackCloudClientContextProvider(),
    );
  });

  test('请求携带平台版本构建号但不把端侧地域运营商用于灰度', () {
    CloudClientContextRegistry.configure(const _HeaderClientContext());

    final headers = CloudRequestHeaders.forPage('runtime.transport.headers');

    expect(headers['X-Client-Device-Platform'], 'android');
    expect(headers['X-Client-App-Version'], '1.9.0');
    expect(headers['X-Client-App-Build'], '19000');
    expect(headers['X-Client-Region-Code'], isNull);
    expect(headers['X-Client-Carrier'], isNull);
  });
}
