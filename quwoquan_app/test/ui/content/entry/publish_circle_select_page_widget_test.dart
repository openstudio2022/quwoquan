import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/pages/publish_circle_select_page.dart';

void main() {
  late FlutterExceptionHandler? originalOnError;

  setUp(() {
    HttpOverrides.global = _NoNetworkHttpOverrides();
    originalOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      final message = details.exceptionAsString();
      if (message.contains('HTTP request failed') ||
          message.contains('NetworkImageLoadException')) {
        return;
      }
      originalOnError?.call(details);
    };
  });

  tearDown(() {
    HttpOverrides.global = null;
    FlutterError.onError = originalOnError;
  });

  testWidgets('同步圈子页使用返回页样式并展示封面与创作数', (tester) async {
    await tester.pumpWidget(
      _buildApp(
        PublishCircleSelectPage(
          joinedCircles: _joinedCircles,
          initialSelected: const <String, String>{},
          recommendedCircles: _recommendedCircles,
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(TestKeys.publishCircleSelectPage), findsOneWidget);
    expect(find.byIcon(CupertinoIcons.xmark), findsNothing);
    expect(find.byType(CircleMediaImage), findsWidgets);
    expect(find.textContaining('件作品'), findsWidgets);
    expect(find.byKey(TestKeys.publishCircleCancelButton), findsOneWidget);
    expect(find.byKey(TestKeys.publishCircleConfirmButton), findsOneWidget);
  });

  testWidgets('同步圈子页多选后可通过底部确认返回', (tester) async {
    await tester.pumpWidget(_buildApp(const _PublishCircleHarness()));
    await tester.tap(find.text('打开圈子选择'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('摄影圈'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('CityWalk圈'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(TestKeys.publishCircleConfirmButton));
    await tester.pumpAndSettle();

    expect(find.text('result:circle-photo,circle-citywalk'), findsOneWidget);
  });
}

Widget _buildApp(Widget home) {
  return MaterialApp(
    locale: const Locale('zh'),
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: home,
  );
}

class _PublishCircleHarness extends StatefulWidget {
  const _PublishCircleHarness();

  @override
  State<_PublishCircleHarness> createState() => _PublishCircleHarnessState();
}

class _PublishCircleHarnessState extends State<_PublishCircleHarness> {
  String _resultText = 'result:none';

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            ElevatedButton(
              onPressed: () async {
                final result = await Navigator.of(context)
                    .push<Map<String, String>?>(
                      MaterialPageRoute<Map<String, String>?>(
                        builder: (_) => PublishCircleSelectPage(
                          joinedCircles: _joinedCircles,
                          initialSelected: const <String, String>{},
                          recommendedCircles: _recommendedCircles,
                        ),
                      ),
                    );
                if (!mounted) {
                  return;
                }
                setState(() {
                  _resultText = result == null
                      ? 'result:none'
                      : 'result:${result.keys.join(',')}';
                });
              },
              child: const Text('打开圈子选择'),
            ),
            const SizedBox(height: 12),
            Text(_resultText),
          ],
        ),
      ),
    );
  }
}

const List<CreateCircleOption> _joinedCircles = <CreateCircleOption>[
  CreateCircleOption(
    id: 'circle-photo',
    name: '摄影圈',
    memberCount: 128,
    postCount: 36,
    coverUrl:
        'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?q=80&w=400',
  ),
  CreateCircleOption(
    id: 'circle-citywalk',
    name: 'CityWalk圈',
    memberCount: 214,
    postCount: 67,
    coverUrl:
        'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?q=80&w=400',
  ),
];

const List<CreateCircleOption> _recommendedCircles = <CreateCircleOption>[
  CreateCircleOption(
    id: 'circle-food',
    name: '美食圈',
    memberCount: 89,
    postCount: 21,
    recommendationReason: '同城热门',
    isJoined: false,
    coverUrl:
        'https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=600',
  ),
];

class _NoNetworkHttpOverrides extends HttpOverrides {}
