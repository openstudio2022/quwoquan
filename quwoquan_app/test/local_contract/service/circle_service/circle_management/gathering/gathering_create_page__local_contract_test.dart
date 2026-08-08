import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_create_page.dart';

import '../../../../../support/service/circle_service/circle_management/gathering/gathering_test_support.dart';

GatheringCreatePage _page({int maxParticipants = 4}) {
  final seed = gatheringInitialSeedData(maxParticipants: maxParticipants);
  return GatheringCreatePage(
    copy: gatheringCreateTestCopy,
    initialValue: GatheringCreateInitialValue(
      host: seed.host,
      creatorParticipates: seed.creatorParticipates,
      purpose: seed.purpose,
      schedule: seed.schedule,
      place: seed.place,
      policy: seed.policy,
    ),
  );
}

void main() {
  group('GatheringCreatePage local_contract', () {
    testWidgets('room readiness 未有 canonical App owner 时保留 draft 且不伪发布', (
      tester,
    ) async {
      final port = InMemoryGatheringPort();
      await pumpGatheringWidget(
        tester,
        port: port,
        child: _page(maxParticipants: 1),
      );

      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.pumpAndSettle();

      expect(port.createCalls, 1);
      expect(port.queryCalls, 0);
      expect(port.publishCalls, 0);
      expect(port.lastCreate?.policy.maxParticipants, 1);
      expect(port.lastCreate?.creatorParticipates, isTrue);
      expect(port.lastCreate?.idempotencyKey, startsWith('gathering-create-'));
      expect(find.text(gatheringCreateTestCopy.roomStepLabel), findsOneWidget);
      expect(find.byKey(GatheringCreatePage.retryKey), findsOneWidget);
    });

    testWidgets('room pending 重试不重复 draft 且继续 fail-closed', (tester) async {
      final port = InMemoryGatheringPort();
      await pumpGatheringWidget(tester, port: port, child: _page());

      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.pumpAndSettle();

      expect(port.createCalls, 1);
      expect(port.queryCalls, 0);
      expect(port.publishCalls, 0);
      expect(find.byKey(GatheringCreatePage.retryKey), findsOneWidget);

      await tester.tap(find.byKey(GatheringCreatePage.retryKey));
      await tester.pumpAndSettle();

      expect(port.createCalls, 1);
      expect(port.queryCalls, 0);
      expect(port.publishCalls, 0);
      expect(find.byKey(GatheringCreatePage.retryKey), findsOneWidget);
    });

    testWidgets('重复点击只提交一个创建 intent', (tester) async {
      final gate = Completer<void>();
      final port = InMemoryGatheringPort()..createGate = gate;
      await pumpGatheringWidget(tester, port: port, child: _page());

      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.tap(find.byKey(GatheringCreatePage.submitKey));
      await tester.pump();

      expect(port.createCalls, 1);

      gate.complete();
      await tester.pumpAndSettle();
      expect(port.createCalls, 1);
      expect(port.queryCalls, 0);
      expect(port.publishCalls, 0);
    });
  });
}
