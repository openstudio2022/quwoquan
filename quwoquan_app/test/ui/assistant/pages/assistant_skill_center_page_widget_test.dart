import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/assistant/pages/assistant_skill_center_page.dart';

Widget _buildApp(AssistantRepository repository) {
  return ProviderScope(
    overrides: [assistantRepositoryProvider.overrideWithValue(repository)],
    child: MaterialApp(
      locale: const Locale('zh'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: AssistantSkillCenterPage(onBack: () {}),
    ),
  );
}

void main() {
  testWidgets('技能中心通过统一 AssistantRepository 展示订阅状态', (tester) async {
    final repository = MockAssistantRepository();
    await repository.createSkillSubscription(
      skillId: 'stock_sentinel',
      domainId: 'finance',
      rawText: '每天开盘前提醒我关注的股票重大消息',
    );

    await tester.pumpWidget(_buildApp(repository));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 200));

    expect(find.text('股票哨兵'), findsOneWidget);
    expect(find.textContaining('已订阅'), findsWidgets);
    expect(find.text('出行旅程管家'), findsOneWidget);
    expect(find.byType(CupertinoSwitch), findsWidgets);
  });
}
