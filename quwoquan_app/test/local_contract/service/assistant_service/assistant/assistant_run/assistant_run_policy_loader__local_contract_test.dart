import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_run_policy_loader.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/assistant_run_policy_text_source.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/progress_text_policy.dart';

void main() {
  test('loader parses once and shares one in-flight source read', () async {
    final response = Completer<String>();
    final source = _PolicyTextSource((_) => response.future);
    final loader = AssistantRunPolicyLoader(
      source: source,
      path: 'policy.json',
    );

    final first = loader.load();
    final second = loader.load();
    expect(source.readCount, 1);
    response.complete(
      jsonEncode(<String, Object?>{
        'jsonEnvelopeSignatures': <String>['"loaded"'],
      }),
    );

    final policies = await Future.wait<ProgressTextPolicy>(
      <Future<ProgressTextPolicy>>[first, second],
    );
    expect(policies[0].jsonEnvelopeSignatures, <String>['"loaded"']);
    expect(identical(policies[0], policies[1]), isTrue);

    expect(await loader.load(), same(policies[0]));
    expect(source.readCount, 1);
  });

  test('loader falls back to defaults for malformed policy text', () async {
    final loader = AssistantRunPolicyLoader(
      source: _PolicyTextSource((_) async => '{invalid'),
      path: 'policy.json',
    );

    expect(await loader.load(), same(ProgressTextPolicy.defaults));
  });

  test('loader falls back to defaults when the source rejects', () async {
    final loader = AssistantRunPolicyLoader(
      source: _PolicyTextSource(
        (_) => Future<String>.error(StateError('missing')),
      ),
      path: 'policy.json',
    );

    expect(await loader.load(), same(ProgressTextPolicy.defaults));
  });
}

final class _PolicyTextSource implements AssistantRunPolicyTextSource {
  _PolicyTextSource(this._read);

  final Future<String> Function(String path) _read;
  int readCount = 0;

  @override
  Future<String> read(String path) {
    readCount += 1;
    return _read(path);
  }
}
