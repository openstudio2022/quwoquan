import 'dart:async';

import 'package:quwoquan_app/personal_assistant/app/assistant_gateway.dart';
import 'package:quwoquan_app/personal_assistant/connectors/openclaw_bridge.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_request.dart';
import 'package:quwoquan_app/personal_assistant/protocol/run_response.dart';
import 'package:quwoquan_app/personal_assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/personal_assistant/tools/tool_schema.dart';

enum CapabilityRouteMode {
  localOnly,
  remotePreferred,
  hybrid,
}

enum AssistantRunStreamEventType { trace, completed, failed }

class AssistantRunStreamEvent {
  const AssistantRunStreamEvent._({
    required this.type,
    this.trace,
    this.response,
    this.errorMessage,
  });

  factory AssistantRunStreamEvent.trace(AssistantTraceEvent trace) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.trace,
        trace: trace,
      );

  factory AssistantRunStreamEvent.completed(AssistantRunResponse response) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.completed,
        response: response,
      );

  factory AssistantRunStreamEvent.failed(String errorMessage) =>
      AssistantRunStreamEvent._(
        type: AssistantRunStreamEventType.failed,
        errorMessage: errorMessage,
      );

  final AssistantRunStreamEventType type;
  final AssistantTraceEvent? trace;
  final AssistantRunResponse? response;
  final String? errorMessage;
}

class CapabilityGateway {
  CapabilityGateway({
    required AssistantGateway assistantGateway,
    required OpenClawBridge openClawBridge,
  })  : _assistantGateway = assistantGateway,
        _openClawBridge = openClawBridge {
    _openClawBridge.bindLocalGateway(assistantGateway);
  }

  final AssistantGateway _assistantGateway;
  final OpenClawBridge _openClawBridge;

  bool _isRemoteResponseCommercialReady(AssistantRunResponse response) {
    if (response.degraded) return false;
    final structured = response.structuredResponse;
    final dialogueRuntime =
        (structured['dialogueRuntime'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final domainId = (dialogueRuntime['domainId'] as String?)?.trim() ?? '';
    final uiAnswer = (structured['uiAnswer'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final markdown = (uiAnswer['markdownText'] as String?)?.trim() ?? '';
    final hasRawTraceLikePrefix = RegExp(
      r'^\s*\[(page|memory|tool|trace)\.',
      caseSensitive: false,
    ).hasMatch(response.finalText);
    return domainId.isNotEmpty && markdown.isNotEmpty && !hasRawTraceLikePrefix;
  }

  Future<AssistantRunResponse> run({
    required AssistantRunRequest request,
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) async {
    if (mode == CapabilityRouteMode.localOnly) {
      return _safeLocalRun(request);
    }
    if (mode == CapabilityRouteMode.remotePreferred) {
      final remote = await _safeRemoteRun(request);
      if (remote != null && _isRemoteResponseCommercialReady(remote)) {
        return remote;
      }
      return _safeLocalRun(request);
    }
    final local = await _safeLocalRun(request);
    if (local.degraded) {
      final remote = await _safeRemoteRun(request);
      if (remote != null && _isRemoteResponseCommercialReady(remote)) {
        return remote;
      }
    }
    return local;
  }

  Stream<AssistantRunStreamEvent> runStream({
    required AssistantRunRequest request,
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) {
    final controller = StreamController<AssistantRunStreamEvent>();
    () async {
      try {
        if (mode == CapabilityRouteMode.localOnly) {
          final local = await _runLocalWithStream(request, controller);
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        if (mode == CapabilityRouteMode.remotePreferred) {
          final remote = await _safeRemoteRun(request);
          if (remote != null && _isRemoteResponseCommercialReady(remote)) {
            for (final trace in remote.traces) {
              controller.add(AssistantRunStreamEvent.trace(trace));
            }
            controller.add(AssistantRunStreamEvent.completed(remote));
            return;
          }
          final local = await _runLocalWithStream(request, controller);
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        final local = await _runLocalWithStream(request, controller);
        if (!local.degraded) {
          controller.add(AssistantRunStreamEvent.completed(local));
          return;
        }
        final remote = await _safeRemoteRun(request);
        if (remote != null && _isRemoteResponseCommercialReady(remote)) {
          for (final trace in remote.traces) {
            controller.add(AssistantRunStreamEvent.trace(trace));
          }
          controller.add(AssistantRunStreamEvent.completed(remote));
        } else {
          controller.add(AssistantRunStreamEvent.completed(local));
        }
      } catch (error) {
        controller.add(AssistantRunStreamEvent.failed(error.toString()));
      } finally {
        if (!controller.isClosed) {
          await controller.close();
        }
      }
    }();
    return controller.stream;
  }

  Future<AssistantRunResponse> _safeLocalRun(AssistantRunRequest request) async {
    try {
      return await _assistantGateway.run(request);
    } catch (error) {
      return AssistantRunResponse(
        finalText: '助手暂时不可用，请稍后重试。',
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'local_gateway_error: $error',
            timestamp: DateTime.now(),
            data: <String, dynamic>{
              'suppressed': true,
            },
          ),
        ],
      );
    }
  }

  Future<AssistantRunResponse> _runLocalWithStream(
    AssistantRunRequest request,
    StreamController<AssistantRunStreamEvent> controller,
  ) async {
    try {
      return await _assistantGateway.runWithTraceStream(
        request,
        onTraceEvent: (event) {
          if (!controller.isClosed) {
            controller.add(AssistantRunStreamEvent.trace(event));
          }
        },
      );
    } catch (error) {
      final fallback = AssistantRunResponse(
        finalText: '助手暂时不可用，请稍后重试。',
        degraded: true,
        errorCode: AssistantErrorCode.executionFailed.name,
        traces: <AssistantTraceEvent>[
          AssistantTraceEvent(
            type: AssistantTraceEventType.toolError,
            message: 'local_gateway_error: $error',
            timestamp: DateTime.now(),
            data: <String, dynamic>{'suppressed': true},
          ),
        ],
      );
      for (final trace in fallback.traces) {
        controller.add(AssistantRunStreamEvent.trace(trace));
      }
      return fallback;
    }
  }

  Future<AssistantRunResponse?> _safeRemoteRun(AssistantRunRequest request) async {
    try {
      return await _openClawBridge.runRemote(request);
    } catch (_) {
      return null;
    }
  }

  Future<AssistantToolResult> invokeSkill({
    required String skillId,
    required Map<String, dynamic> arguments,
    String deviceProfile = 'mobile',
    CapabilityRouteMode mode = CapabilityRouteMode.hybrid,
  }) async {
    if (mode == CapabilityRouteMode.localOnly) {
      return _assistantGateway.invokeSkill(
        skillId: skillId,
        arguments: arguments,
        deviceProfile: deviceProfile,
      );
    }
    if (mode == CapabilityRouteMode.remotePreferred) {
      final remote = await _openClawBridge.invokeSkillRemote(
        skillId: skillId,
        arguments: arguments,
      );
      if (remote != null && remote['success'] == true) {
        return AssistantToolResult.fromJson(remote.cast<String, dynamic>());
      }
      return _assistantGateway.invokeSkill(
        skillId: skillId,
        arguments: arguments,
        deviceProfile: deviceProfile,
      );
    }
    final local = await _assistantGateway.invokeSkill(
      skillId: skillId,
      arguments: arguments,
      deviceProfile: deviceProfile,
    );
    if (!local.success) {
      final remote = await _openClawBridge.invokeSkillRemote(
        skillId: skillId,
        arguments: arguments,
      );
      if (remote != null) {
        return AssistantToolResult.fromJson(remote.cast<String, dynamic>());
      }
    }
    return local;
  }
}

