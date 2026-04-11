import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/assistant/models/assistant_context_scope_read_view.dart';

void main() {
  test('AssistantContextScopeReadView reads privacyPolicy, tags, pageType', () {
    final view = AssistantContextScopeReadView(<String, dynamic>{
      'privacyPolicy': <String, dynamic>{
        'allowedReferenceHosts': <String>['example.com'],
      },
      'userTags': <dynamic>[' a ', '', 'b'],
      'pageType': 'create',
    });
    expect(view.privacyPolicy['allowedReferenceHosts'], ['example.com']);
    expect(view.normalizedUserTags, ['a', 'b']);
    expect(view.pageType, 'create');
  });

  test('defaults when keys missing', () {
    final view = AssistantContextScopeReadView(<String, dynamic>{});
    expect(view.privacyPolicy, isEmpty);
    expect(view.normalizedUserTags, isEmpty);
    expect(view.pageType, 'chat');
  });
}
