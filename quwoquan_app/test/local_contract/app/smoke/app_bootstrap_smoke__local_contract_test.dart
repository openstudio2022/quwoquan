import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// 与 `main_prod` 同构的数据源覆盖：ProviderScope + 恒 Remote Notifier。
void main() {
  testWidgets('prod-style appDataSource override builds ProviderScope', (
    tester,
  ) async {
    final overrides = <Override>[
      appDataSourceModeProvider.overrideWith(_SmokeLockedRemote.new),
    ];
    await tester.pumpWidget(
      ProviderScope(
        overrides: overrides,
        child: const MaterialApp(home: Scaffold(body: Text('smoke'))),
      ),
    );
    expect(find.text('smoke'), findsOneWidget);
  });
}

final class _SmokeLockedRemote extends AppDataSourceModeNotifier {
  @override
  AppDataSourceMode build() => AppDataSourceMode.remote;
}
