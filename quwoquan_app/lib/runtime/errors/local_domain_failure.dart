import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/domain_error_code.dart';

/// 端侧**本地判定**出的领域失败 → 与同一 stable code 的 wire 响应完全同源的
/// [CloudException]。
///
/// 存在的理由：有些领域结论端上已经能确定（关系已拉黑、通话人数已满、当前
/// 状态不允许该操作），并不需要真的打一次网络请求才知道。但这类分支过去会
/// 直接手写 `UiErrorSemantic(title: ..., message: ...)`，于是同一个业务失败
/// 出现两套语义：
///
///   - 云端返回 `RTC.USER.blocked` 时，走 `CloudErrorMapper`，页面拿到带
///     `sourceCode` / `recoveryAction` 的 semantic，埋点能按错误码聚合；
///   - 端侧本地判定同一件事时，只剩一个字符串，`sourceCode` 为 null，
///     埋点里这类失败凭空消失，恢复动作也只能靠页面自己猜。
///
/// 本函数把本地分支接回同一条链：由 canonical `MODULE.KIND.REASON` 与其声明的
/// HTTP status 出发，复用 [CloudErrorMapper] 的同一套推导，因此本地判定与
/// 远端返回**在构造上**不可能分叉。
///
/// 只接受已在所属服务 `errors.yaml` 声明、并已生成进 [DomainErrorCodeRegistry]
/// 的错误码：未登记的码会抛 [ArgumentError]，避免这里变成绕过 contracts 凭空
/// 造码的后门。动态上下文不进 code，只走 `context.attributes`。
CloudException localDomainCloudException(String code) {
  final trimmed = code.trim();
  final declared = DomainErrorCodeRegistry.fromCode(trimmed);
  if (declared == null) {
    throw ArgumentError.value(
      code,
      'code',
      'Not a declared domain error code; add it to the owning service '
          'errors.yaml and re-run codegen before using it locally',
    );
  }
  return CloudErrorMapper.fromDecodedStatusCode(
    declared.httpStatus,
    body: <String, Object?>{'code': declared.code},
  );
}
