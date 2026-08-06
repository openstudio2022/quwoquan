import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CreateContentOutboundShareCommand, OutboundShareFactResult;

/// 记录一次已由外部渠道确认完成的内容分享事实。
///
/// presentation 只依赖此对象公开端口；generated client 的具体实现由
/// `runtime/di` 组合根注入。
abstract interface class ContentOutboundShareAppender {
  Future<OutboundShareFactResult> appendOutboundShare(
    CreateContentOutboundShareCommand command,
  );
}
