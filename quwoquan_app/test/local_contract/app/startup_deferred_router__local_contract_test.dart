import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/app/navigation/app_router_module.dart';

void main() {
  test('load deferred router library', () async {
    expect(isAppRouterLibraryLoaded, isFalse);
    await ensureAppRouterLibraryLoaded();
    expect(isAppRouterLibraryLoaded, isTrue);
  });
}
