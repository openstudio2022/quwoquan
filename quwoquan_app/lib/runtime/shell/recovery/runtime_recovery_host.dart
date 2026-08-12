import 'dart:async';

import 'package:flutter/material.dart';
import 'package:quwoquan_app/runtime/shell/recovery/recovery_state_machine.dart';
import 'package:quwoquan_app/runtime/shell/recovery/startup_recovery_page.dart';
import 'package:quwoquan_app/runtime/shell/recovery/startup_recovery_controller.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart'
    as ops_contracts;

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

  void enterClientUpgradeRequired({
    required Object error,
    required StackTrace stack,
    required String source,
    required String failureCode,
  }) {
    _host?.enterClientUpgradeRequired(
      error: error,
      stack: stack,
      source: source,
      failureCode: failureCode,
    );
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
    this.clientUpgradeControllerFactory,
  });

  final Widget Function(Key generationKey, bool isRuntimeReentry) childBuilder;
  final Duration reentryDeadline;
  final StartupRecoveryController Function()? clientUpgradeControllerFactory;

  @override
  State<RuntimeRecoveryHost> createState() => _RuntimeRecoveryHostState();
}

class _RuntimeRecoveryHostState extends State<RuntimeRecoveryHost> {
  StartupRecoveryController? _controller;
  int _generation = 0;
  bool _childMounted = true;
  bool _runtimeReentryConsumed = false;
  String _failureCode = '';
  String _failureSource = 'runtime_boundary';
  Timer? _reentryTimer;
  late Widget _generationChild;

  @override
  void initState() {
    super.initState();
    _generationChild = _buildGenerationChild();
    RuntimeRecoveryCoordinator.instance._attach(this);
  }

  Widget _buildGenerationChild() {
    final generationKey = ValueKey<int>(_generation);
    return KeyedSubtree(
      key: generationKey,
      child: widget.childBuilder(generationKey, _generation > 0),
    );
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
    setState(() {
      _childMounted = false;
      _failureCode = '';
      _failureSource = source;
      _controller = StartupRecoveryController(
        initialSnapshot: RecoverySnapshot(
          phase: _runtimeReentryConsumed
              ? RecoveryPhase.runtimeVersionChecking
              : RecoveryPhase.runtimeUnavailable,
        ),
        onRuntimeReenter: _beginRuntimeReentry,
      );
    });
  }

  void enterClientUpgradeRequired({
    required Object error,
    required StackTrace stack,
    required String source,
    required String failureCode,
  }) {
    if (!mounted || _controller?.requiredUpdateOnly == true) return;
    final previous = _controller;
    final next =
        widget.clientUpgradeControllerFactory?.call() ??
        StartupRecoveryController(
          initialSnapshot: const RecoverySnapshot(
            phase: RecoveryPhase.runtimeVersionChecking,
          ),
          requiredUpdateOnly: true,
        );
    setState(() {
      _childMounted = false;
      _failureCode = failureCode;
      _failureSource = source;
      _controller = next;
    });
    previous?.dispose();
  }

  Future<void> _beginRuntimeReentry() async {
    if (!mounted) throw StateError('runtime recovery host is disposed');
    if (_runtimeReentryConsumed) {
      throw StateError('runtime reentry budget is already consumed');
    }
    setState(() {
      _runtimeReentryConsumed = true;
      _generation += 1;
      _generationChild = _buildGenerationChild();
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
        if (_childMounted) _generationChild else const SizedBox.expand(),
        if (controller != null)
          Positioned.fill(
            child: MaterialApp(
              debugShowCheckedModeBanner: false,
              home: StartupRecoveryPage(
                mount: ops_contracts.StartupRecoveryMount.runtimeBoundary,
                controller: controller,
                failureCode: _failureCode,
                failureSource: _failureSource,
              ),
            ),
          ),
      ],
    );
  }
}
