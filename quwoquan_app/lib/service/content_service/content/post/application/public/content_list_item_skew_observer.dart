import 'dart:async';

import 'package:quwoquan_app/runtime/observability/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_list_item_decoder.dart';

/// 列表项被隔离时的 canonical 契约偏差观测。
///
/// 只记录对象标识与类型化原因，不写入正文、作者或任何 PII。
final class ContentListItemSkewObserver {
  const ContentListItemSkewObserver();

  static const String source = 'content.list_item.presentation_skew';

  void record(
    List<ContentListItemIsolation> isolated, {
    required String operationId,
  }) {
    if (isolated.isEmpty) {
      return;
    }
    for (final isolation in isolated) {
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: source,
          error: ContentListItemSkew(isolation),
          stackTrace: StackTrace.empty,
          operationId: operationId,
        ),
      );
    }
  }
}

/// 被隔离项的观测载体；不是用户可见错误，也不向上抛断整页。
final class ContentListItemSkew implements Exception {
  const ContentListItemSkew(this.isolation);

  final ContentListItemIsolation isolation;

  @override
  String toString() => 'ContentListItemSkew(${isolation.toString()})';
}
