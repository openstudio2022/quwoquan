import 'dart:convert';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_models.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_page_experience_tracker.dart';

/// 客户端可见业务域的**错误链端到端**探针。
///
/// 一条用例贯通全链，任何一环断裂都会在同一个断言里暴露：
///
/// ```text
/// HTTP 错误响应(status + canonical RuntimeErrorResponse body)
///   -> CloudErrorMapper           (得到带 code / runtimeFailure 的 CloudException)
///   -> UiErrorSemanticResolver    (得到 UiErrorSemantic：标题/文案/恢复动作)
///   -> 恢复动作                    (primaryAction / recoveryAction)
///   -> 埋点属性                    (PageLifecycleObservability 真实上报的 properties)
/// ```
///
/// 之所以必须端到端而不是分段断言：这条链上每一环单独看都"有代码"，
/// 但真正的回归模式是**环之间的语义丢失**——mapper 拿到了 code，resolver 却
/// 没把它带进 `sourceCode`，于是埋点里这个错误码凭空消失。分段测试全绿、
/// 线上按错误码聚合却查不到，正是这类缺口。
///
/// 埋点这一环刻意走真实的 [PageLifecycleObservability.recordPageState]，
/// 而不是复述一份属性映射：后者只会把同样的错误在测试里再写一遍。
@immutable
final class ErrorChainOutcome {
  const ErrorChainOutcome({
    required this.exception,
    required this.semantic,
    required this.telemetryProperties,
  });

  /// `CloudErrorMapper` 对 HTTP 响应的映射结果。
  final CloudException exception;

  /// 页面实际消费的展示语义。
  final UiErrorSemantic semantic;

  /// `page_lifecycle` 事件真实上报的属性。
  final Map<String, dynamic> telemetryProperties;

  /// 埋点里用于按错误码聚合的维度。
  String? get telemetrySourceCode =>
      telemetryProperties['sourceCode'] as String?;

  String? get telemetryRecoveryAction =>
      telemetryProperties['recoveryAction'] as String?;

  String? get telemetryFailureKind =>
      telemetryProperties['failureKind'] as String?;

  String? get telemetryTraceId => telemetryProperties['traceId'] as String?;

  String? get telemetryRequestId => telemetryProperties['requestId'] as String?;
}

/// 构造一个 canonical `RuntimeErrorResponse` wire body。
///
/// 形状必须与云侧 `runtime/errors` 出口一致，否则测的就不是真实链路：
/// `location` 与 `context` 两个 Map 是 `CloudErrorMapper` 识别 canonical
/// runtime 错误响应的判据，缺一个就会退化成"只认得 code"的降级路径。
String canonicalRuntimeErrorBody({
  required String code,
  required String origin,
  required String kind,
  required String nature,
  required String businessObject,
  required String functionModule,
  String reason = '',
  String userMessage = '',
  String requestId = '',
  String traceId = '',
  String recoveryAction = '',
  int recoveryAfterSeconds = 0,
  String disruptionLevel = '',
  Map<String, String> contextAttributes = const <String, String>{},
}) {
  return jsonEncode(<String, Object?>{
    'code': code,
    'reason': reason,
    'origin': origin,
    'kind': kind,
    'nature': nature,
    'requestId': requestId,
    'traceId': traceId,
    'userMessage': userMessage,
    'location': <String, Object?>{
      'businessObject': businessObject,
      'functionModule': functionModule,
    },
    // 动态上下文只允许以 string-only attributes 出现，不得进 code 或用户提示。
    'context': <String, Object?>{
      'attributes': contextAttributes.entries
          .map((entry) => <String, Object?>{'key': entry.key, 'value': entry.value})
          .toList(growable: false),
    },
    'recovery': <String, Object?>{
      'action': recoveryAction,
      'afterSeconds': recoveryAfterSeconds,
      'disruptionLevel': disruptionLevel,
    },
  });
}

/// 只记录、不外发的 analytics 替身（对象级最小 typed double）。
final class RecordingAnalyticsService extends AnalyticsService {
  RecordingAnalyticsService() : super.forTesting();

  final List<AnalyticsEvent> events = <AnalyticsEvent>[];

  @override
  Future<void> trackEvent(AnalyticsEvent event) async {
    events.add(event);
  }
}

/// 跑完整条错误链，返回每一环的真实产物。
///
/// [statusCode] / [body] 是被测的 HTTP 错误响应；[category] / [scope] 是页面
/// 消费该错误时声明的展示语境。
Future<ErrorChainOutcome> runErrorChain(
  WidgetTester tester, {
  required int statusCode,
  required String body,
  required UiErrorCategory category,
  required UiErrorScope scope,
  String? requestPath,
  String pageName = 'error_chain_probe_page',
  String? route,
  String? surface,
  bool allowRetry = true,
}) async {
  return runErrorChainForError(
    tester,
    error: CloudErrorMapper.fromStatusCode(
      statusCode,
      body: body,
      requestPath: requestPath,
    ),
    category: category,
    scope: scope,
    pageName: pageName,
    route: route,
    surface: surface,
    allowRetry: allowRetry,
  );
}

/// 从一个已经映射好的 [CloudException] 起跑后半条链。
///
/// 端侧本地判定的失败（`localDomainCloudException`）没有 HTTP 响应可言，
/// 但必须与同码的远端响应产出**同一套**展示语义与埋点属性，因此复用这里。
Future<ErrorChainOutcome> runErrorChainForError(
  WidgetTester tester, {
  required CloudException error,
  required UiErrorCategory category,
  required UiErrorScope scope,
  String pageName = 'error_chain_probe_page',
  String? route,
  String? surface,
  bool allowRetry = true,
}) async {
  final exception = error;

  late UiErrorSemantic semantic;
  await tester.pumpWidget(
    CupertinoApp(
      home: Builder(
        builder: (context) {
          semantic = runtimeErrorSemantic(
            context,
            error: exception,
            category: category,
            scope: scope,
            allowRetry: allowRetry,
          );
          return const SizedBox.shrink();
        },
      ),
    ),
  );

  final analytics = RecordingAnalyticsService();
  PageLifecycleObservability(
    analytics: analytics,
    pageExperienceTracker: AppPageExperienceTracker.instance,
  ).recordPageState(
    pageName: pageName,
    phase: 'error',
    route: route,
    surface: surface,
    error: semantic,
  );

  expect(
    analytics.events,
    hasLength(1),
    reason: '错误态必须恰好上报一次 page_lifecycle 事件',
  );

  return ErrorChainOutcome(
    exception: exception,
    semantic: semantic,
    telemetryProperties: analytics.events.single.properties,
  );
}

/// 每个客户端可见业务域的最小共同断言。
///
/// 逐域用例只需补该域**特有**的期望（错误码、恢复动作、文案来源），
/// 共性不变量集中在这里，避免 N 份复制粘贴各自漂移。
void expectErrorChainIsIntact(
  ErrorChainOutcome outcome, {
  required String expectedCode,
  required String domainLabel,
}) {
  // 1. mapper 必须认出 canonical stable code，而不是退化成传输层错误。
  expect(
    outcome.exception.code,
    expectedCode,
    reason: '$domainLabel: CloudErrorMapper 未识别 canonical stable code',
  );
  expect(
    outcome.exception.runtimeFailure,
    isNotNull,
    reason: '$domainLabel: CloudErrorMapper 未产出 runtimeFailure，'
        '后续恢复动作与埋点将全部失去依据',
  );

  // 2. resolver 必须把错误码带进展示语义，否则页面无法归因。
  expect(
    outcome.semantic.sourceCode,
    expectedCode,
    reason: '$domainLabel: UiErrorSemantic 丢失 sourceCode',
  );

  // 3. 必须给出用户可读文案，且不得把 stable code 泄露到界面上。
  expect(
    outcome.semantic.message.trim(),
    isNotEmpty,
    reason: '$domainLabel: 错误态缺少用户可读文案',
  );
  expect(
    outcome.semantic.message,
    isNot(contains(expectedCode)),
    reason: '$domainLabel: stable code 不得直接呈现给用户',
  );

  // 4. 必须存在恢复路径：要么有主动作，要么有明确的 recoveryAction 语义。
  expect(
    outcome.semantic.primaryAction != null ||
        outcome.semantic.secondaryAction != null ||
        outcome.semantic.recoveryAction != null,
    isTrue,
    reason: '$domainLabel: 错误态没有任何恢复路径，用户会卡死在该状态',
  );

  // 5. 埋点必须能按错误码聚合——这是线上排障的唯一入口。
  expect(
    outcome.telemetrySourceCode,
    expectedCode,
    reason: '$domainLabel: 埋点未携带 sourceCode，线上无法按错误码聚合',
  );
  expect(
    outcome.telemetryFailureKind,
    isNotNull,
    reason: '$domainLabel: 埋点未携带 failureKind',
  );
}
