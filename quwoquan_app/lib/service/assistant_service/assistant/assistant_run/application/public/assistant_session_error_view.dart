/// AssistantSession 错误卡只消费这两个稳定展示字段。
abstract interface class AssistantSessionErrorView {
  String get errorMessage;

  Object? get errorFailure;
}
