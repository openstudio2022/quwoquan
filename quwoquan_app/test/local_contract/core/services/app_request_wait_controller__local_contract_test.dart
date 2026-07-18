import 'package:fake_async/fake_async.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/services/app_request_wait_controller.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

void main() {
  group('AppRequestWaitController', () {
    test('本地查找 1499ms 仍可完成，1500ms 必须结算', () {
      fakeAsync((async) {
        final controller = _controller(async);
        var timedOut = false;
        final generation = controller.start(
          mode: AppRequestWaitMode.foreground,
          deadline: AppRequestWaitTimings.localLookupDeadline,
          showSlowHint: false,
          onTimeout: (_) => timedOut = true,
        );

        async.elapse(const Duration(milliseconds: 1499));
        expect(controller.isCurrent(generation), isTrue);
        expect(timedOut, isFalse);

        async.elapse(const Duration(milliseconds: 1));
        expect(controller.isPending, isFalse);
        expect(timedOut, isTrue);
      });
    });

    test('2999ms 不提示，3000ms 阻塞态只提示一次', () {
      fakeAsync((async) {
        final controller = _controller(async);
        var slowCount = 0;
        controller.start(
          mode: AppRequestWaitMode.foreground,
          onSlow: (_) => slowCount += 1,
        );

        async.elapse(const Duration(milliseconds: 2999));
        expect(slowCount, 0);
        expect(controller.isSlow, isFalse);

        async.elapse(const Duration(milliseconds: 1));
        expect(slowCount, 1);
        expect(controller.isSlow, isTrue);
        async.elapse(const Duration(seconds: 1));
        expect(slowCount, 1);
      });
    });

    test('5999ms 云读取仍等待，6000ms 取消 transport 并终止', () {
      fakeAsync((async) {
        final controller = _controller(async);
        final cancellation = CloudOperationCancellationSignal();
        var timedOut = false;
        controller.start(
          mode: AppRequestWaitMode.foreground,
          cancellation: cancellation,
          onTimeout: (_) => timedOut = true,
        );

        async.elapse(const Duration(milliseconds: 5999));
        expect(controller.isPending, isTrue);
        expect(cancellation.isCancelled, isFalse);

        async.elapse(const Duration(milliseconds: 1));
        expect(controller.isPending, isFalse);
        expect(cancellation.isCancelled, isTrue);
        expect(timedOut, isTrue);
      });
    });

    test('长任务到 6000ms 不被普通读取期限误杀', () {
      fakeAsync((async) {
        final controller = _controller(async);
        final cancellation = CloudOperationCancellationSignal();
        final generation = controller.start(
          mode: AppRequestWaitMode.longTask,
          cancellation: cancellation,
        );

        async.elapse(const Duration(seconds: 6));
        expect(controller.isCurrent(generation), isTrue);
        expect(cancellation.isCancelled, isFalse);
      });
    });

    test('新请求 supersede 旧请求且旧 completion 不得回写', () {
      fakeAsync((async) {
        final controller = _controller(async);
        final firstCancellation = CloudOperationCancellationSignal();
        final first = controller.start(
          mode: AppRequestWaitMode.foreground,
          cancellation: firstCancellation,
        );
        final second = controller.start(mode: AppRequestWaitMode.foreground);

        expect(firstCancellation.isCancelled, isTrue);
        expect(controller.complete(first), isFalse);
        expect(controller.isCurrent(second), isTrue);
      });
    });

    test('dispose 清理计时器且不触发提示或终止回调', () {
      fakeAsync((async) {
        final controller = _controller(async);
        var slowCount = 0;
        var timeoutCount = 0;
        controller.start(
          mode: AppRequestWaitMode.foreground,
          onSlow: (_) => slowCount += 1,
          onTimeout: (_) => timeoutCount += 1,
        );
        controller.dispose();

        async.elapse(const Duration(seconds: 7));
        expect(slowCount, 0);
        expect(timeoutCount, 0);
      });
    });

    test('action 必须使用 operation metadata deadline', () {
      fakeAsync((async) {
        final controller = _controller(async);
        expect(
          () => controller.start(mode: AppRequestWaitMode.action),
          throwsArgumentError,
        );
      });
    });

    test('action 在 3 秒提示并遵守 operation metadata deadline', () {
      fakeAsync((async) {
        final controller = _controller(async);
        final cancellation = CloudOperationCancellationSignal();
        var slowCount = 0;
        var timeoutCount = 0;
        controller.start(
          mode: AppRequestWaitMode.action,
          deadline: const Duration(seconds: 5),
          cancellation: cancellation,
          onSlow: (_) => slowCount += 1,
          onTimeout: (_) => timeoutCount += 1,
        );

        async.elapse(const Duration(milliseconds: 2999));
        expect(slowCount, 0);
        async.elapse(const Duration(milliseconds: 1));
        expect(slowCount, 1);
        async.elapse(const Duration(milliseconds: 1999));
        expect(controller.isPending, isTrue);
        async.elapse(const Duration(milliseconds: 1));
        expect(timeoutCount, 1);
        expect(cancellation.isCancelled, isTrue);
      });
    });
  });
}

AppRequestWaitController _controller(FakeAsync async) {
  final clock = async.getClock(DateTime.utc(2026, 7, 16));
  return AppRequestWaitController(now: clock.now);
}
