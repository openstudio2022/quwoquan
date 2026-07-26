import 'dart:async';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/app/recovery/recovery_failure_reporter.dart';
import 'package:quwoquan_app/app/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/app/recovery/recovery_surface.dart';
import 'package:quwoquan_app/app/recovery/startup_recovery_controller.dart';

/// 只有明确标记为“无法安全继续”的异常才能穿过全局错误边界进入 R0。
/// 普通 FlutterError、接口失败和可降级错误不会触发本恢复层。
final class UnrecoverableRuntimeException implements Exception {
  const UnrecoverableRuntimeException({
    required this.cause,
    required this.source,
  });

  final Object cause;
  final String source;

  @override
  String toString() => 'UnrecoverableRuntimeException($source)';
}

final class RuntimeRecoveryCoordinator {
  RuntimeRecoveryCoordinator._();

  static final RuntimeRecoveryCoordinator instance =
      RuntimeRecoveryCoordinator._();

  _RuntimeRecoveryHostState? _host;

  void _attach(_RuntimeRecoveryHostState host) => _host = host;

  void _detach(_RuntimeRecoveryHostState host) {
    if (identical(_host, host)) _host = null;
  }

  void enter({
    required Object error,
    required StackTrace stack,
    required String source,
  }) {
    _host?.enter(error: error, stack: stack, source: source);
  }

  void markSafeShellReady() => _host?.markSafeShellReady();
}

/// 根容器在 R0 时销毁异常业务树，R1 时只重建一次 ProviderScope/App Root。
/// 恢复层自身不进入业务 Router，因此成功后无法返回异常页。
class RuntimeRecoveryHost extends StatefulWidget {
  const RuntimeRecoveryHost({
    super.key,
    required this.childBuilder,
    this.reentryDeadline = const Duration(seconds: 8),
  });

  final Widget Function(Key generationKey, bool isRuntimeReentry) childBuilder;
  final Duration reentryDeadline;

  @override
  State<RuntimeRecoveryHost> createState() => _RuntimeRecoveryHostState();
}

class _RuntimeRecoveryHostState extends State<RuntimeRecoveryHost> {
  StartupRecoveryController? _controller;
  int _generation = 0;
  bool _childMounted = true;
  Timer? _reentryTimer;

  @override
  void initState() {
    super.initState();
    RuntimeRecoveryCoordinator.instance._attach(this);
  }

  @override
  void dispose() {
    RuntimeRecoveryCoordinator.instance._detach(this);
    _reentryTimer?.cancel();
    _controller?.dispose();
    super.dispose();
  }

  void enter({
    required Object error,
    required StackTrace stack,
    required String source,
  }) {
    if (!mounted) return;
    final controller = _controller;
    if (controller != null) {
      if (controller.snapshot.phase == RecoveryPhase.runtimeReentering) {
        _reentryTimer?.cancel();
        setState(() {
          _childMounted = false;
          controller.markRuntimeReentryFailed();
        });
      }
      return;
    }
    unawaited(
      RecoveryFailureReporter.instance.record(
        errorSource: 'runtime',
        errorType: error.runtimeType.toString(),
        errorMessage: error.toString(),
        stackTrace: stack.toString(),
      ),
    );
    setState(() {
      _childMounted = false;
      _controller = StartupRecoveryController(
        initialSnapshot: const RecoverySnapshot(
          phase: RecoveryPhase.runtimeUnavailable,
        ),
        onRuntimeReenter: _beginRuntimeReentry,
      );
    });
  }

  Future<void> _beginRuntimeReentry() async {
    if (!mounted) throw StateError('runtime recovery host is disposed');
    setState(() {
      _generation += 1;
      _childMounted = true;
    });
    _reentryTimer?.cancel();
    _reentryTimer = Timer(widget.reentryDeadline, () {
      final controller = _controller;
      if (!mounted ||
          controller?.snapshot.phase != RecoveryPhase.runtimeReentering) {
        return;
      }
      setState(() {
        _childMounted = false;
        controller?.markRuntimeReentryFailed();
      });
    });
    await WidgetsBinding.instance.endOfFrame;
  }

  void markSafeShellReady() {
    final controller = _controller;
    if (!mounted ||
        controller?.snapshot.phase != RecoveryPhase.runtimeReentering) {
      return;
    }
    _reentryTimer?.cancel();
    setState(() {
      _controller = null;
    });
    controller?.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Stack(
      fit: StackFit.expand,
      textDirection: TextDirection.ltr,
      children: <Widget>[
        if (_childMounted)
          KeyedSubtree(
            key: ValueKey<int>(_generation),
            child: widget.childBuilder(
              ValueKey<int>(_generation),
              _generation > 0,
            ),
          )
        else
          const SizedBox.expand(),
        if (controller != null)
          Positioned.fill(
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              home: StartupRecoveryPage(controller: controller),
            ),
          ),
      ],
    );
  }
}
