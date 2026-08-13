/// 对象级 typed fault 注入基建（测试树内共享，不进入环境 App）。
///
/// 故障 profile 与环境边缘 harness 的契约闭集保持同名同义
/// （bandwidth / disconnect / error / latency）；本注入器只服务
/// local_contract 层的对象级 typed double 组合，环境层注入由
/// `stackctl drill` 承载。
///
/// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#req-001
library;

import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../errors/runtime_failure_fixtures.dart';

/// 故障 profile 闭集，与 fault-injection-harness 契约同源。
enum TypedFaultProfile { bandwidth, disconnect, error, latency }

/// 供对象级 typed double 组合的故障注入器。
///
/// 用法：double 的每个被测方法体以 `injector.guard(() => ...)` 包裹；
/// 测试通过 [activate] / [deactivate] 切换故障态，验证重试、超时、
/// 结构化失败与恢复语义。
///
/// 注意：对 FutureProvider 类消费方断言故障时，须在 ProviderContainer
/// 上禁用 Riverpod 自动重试（`retry: (retryCount, error) => null`），
/// 否则失败 provider 会进入指数退避重试，`.future` 读取悬挂直至超时。
class TypedFaultInjector {
  TypedFaultInjector();

  TypedFaultProfile? _active;
  Duration _latency = const Duration(milliseconds: 300);
  String _failureCode = 'APP.SYSTEM.test_failure';
  RuntimeFailureNature _nature = RuntimeFailureNature.transient;

  TypedFaultProfile? get activeProfile => _active;

  /// 激活一种闭集故障 profile。
  ///
  /// [failureCode] 应传入 codegen 错误枚举的 `.code`（如
  /// `ContentPostErrorCode.xxx.code`），保持错误语义与对象 errors.yaml 同源。
  void activate(
    TypedFaultProfile profile, {
    Duration? latency,
    String? failureCode,
    RuntimeFailureNature nature = RuntimeFailureNature.transient,
  }) {
    _active = profile;
    if (latency != null) {
      _latency = latency;
    }
    if (failureCode != null) {
      _failureCode = failureCode;
    }
    _nature = nature;
  }

  void deactivate() => _active = null;

  /// 按激活的 profile 干预一次对象调用。
  Future<T> guard<T>(Future<T> Function() action) async {
    switch (_active) {
      case null:
        return action();
      case TypedFaultProfile.latency:
        await Future<void>.delayed(_latency);
        return action();
      case TypedFaultProfile.bandwidth:
        // 低带宽在对象层表现为响应显著变慢（弱网 profile 的对象级投影）。
        await Future<void>.delayed(_latency * 2);
        return action();
      case TypedFaultProfile.error:
        throw CloudException(
          type: CloudErrorType.server,
          message: 'typed fault injection: server error',
          runtimeFailure: testRuntimeFailure(
            code: _failureCode,
            kind: RuntimeFailureKind.unavailable,
            nature: _nature,
          ),
        );
      case TypedFaultProfile.disconnect:
        throw CloudException(
          type: CloudErrorType.network,
          message: 'typed fault injection: connection unavailable',
          runtimeFailure: testRuntimeFailure(
            code: _failureCode,
            kind: RuntimeFailureKind.unavailable,
            nature: RuntimeFailureNature.transient,
          ),
        );
    }
  }
}
