import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/service/user_service/relationship/greeting_request/application/public/greeting_repository.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_empty_state.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_modal_presenter.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show
        greetingInboxRefreshProvider,
        greetingRepositoryProvider,
        journeyEventTrackerProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:uuid/uuid.dart';

part 'greeting_inbox_page_widgets.dart';

enum _GreetingBox { received, sent }

/// GreetingRequest 的完整收发箱：收到侧支持回复/忽略，发出侧支持撤回，
/// 所有终态均可回显；动作失败不会被吞掉。
class GreetingInboxPage extends ConsumerStatefulWidget {
  const GreetingInboxPage({super.key});

  @override
  ConsumerState<GreetingInboxPage> createState() => _GreetingInboxPageState();
}

class _GreetingInboxPageState extends ConsumerState<GreetingInboxPage> {
  final Set<String> _busyRequestIds = <String>{};
  final Map<String, String> _actionIntentKeys = <String, String>{};
  List<GreetingRequestViewData> _received = const <GreetingRequestViewData>[];
  List<GreetingRequestViewData> _sent = const <GreetingRequestViewData>[];
  _GreetingBox _box = _GreetingBox.received;
  Object? _rawError;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _rawError = null;
    });
    try {
      final repository = ref.read(greetingRepositoryProvider);
      final results = await Future.wait<List<GreetingRequestViewData>>(
        <Future<List<GreetingRequestViewData>>>[
          repository.listInbox(status: '', limit: 100),
          repository.listOutbox(status: '', limit: 100),
        ],
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _received = results[0];
        _sent = results[1];
      });
    } catch (error) {
      if (mounted) {
        setState(() => _rawError = error);
      }
    } finally {
      if (mounted) {
        setState(() => _loading = false);
      }
    }
  }

  Future<void> _reply(GreetingRequestViewData request) async {
    await _runAction(
      request,
      action: 'reply_greeting',
      operation: (idempotencyKey) async {
        final result = await ref
            .read(greetingRepositoryProvider)
            .replyGreeting(request.id, idempotencyKey: idempotencyKey);
        final readback = await _readbackReceived(
          request.id,
          expectedStatus: 'replied',
        );
        final conversationId = readback.promotedConversationId?.trim() ?? '';
        if (conversationId.isEmpty || conversationId != result.conversationId) {
          throw StateError('Greeting reply Remote readback did not converge');
        }
        _replaceReceived(readback);
        ref.read(greetingInboxRefreshProvider).refreshPendingInbox();
        if (!mounted) {
          return;
        }
        AppToast.show(context, ChatText.chatGreetingReplySucceeded);
        context.push(AppRoutePaths.chatDetail(id: conversationId));
      },
    );
  }

  Future<void> _ignore(GreetingRequestViewData request) async {
    await _runAction(
      request,
      action: 'ignore_greeting',
      operation: (idempotencyKey) async {
        await ref
            .read(greetingRepositoryProvider)
            .ignoreGreeting(request.id, idempotencyKey: idempotencyKey);
        final readback = await _readbackReceived(
          request.id,
          expectedStatus: 'ignored',
        );
        if ((readback.promotedConversationId?.trim() ?? '').isNotEmpty) {
          throw StateError('Ignored GreetingRequest created a conversation');
        }
        _replaceReceived(readback);
        ref.read(greetingInboxRefreshProvider).refreshPendingInbox();
        if (mounted) {
          AppToast.show(context, ChatText.chatGreetingIgnored);
        }
      },
    );
  }

  Future<void> _confirmCancel(GreetingRequestViewData request) async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(ChatText.chatGreetingCancelConfirmTitle),
        content: const Text(ChatText.chatGreetingCancelConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(FoundationText.cancel),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text(ChatText.chatGreetingCancel),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) {
      return;
    }
    await _runAction(
      request,
      action: 'cancel_greeting',
      operation: (idempotencyKey) async {
        await ref
            .read(greetingRepositoryProvider)
            .cancelGreeting(request.id, idempotencyKey: idempotencyKey);
        final readback = await _readbackSent(
          request.id,
          expectedStatus: 'cancelled',
        );
        if ((readback.promotedConversationId?.trim() ?? '').isNotEmpty) {
          throw StateError('Cancelled GreetingRequest created a conversation');
        }
        _replaceSent(readback);
        if (mounted) {
          AppToast.show(context, ChatText.chatGreetingCancelled);
        }
      },
    );
  }

  Future<void> _runAction(
    GreetingRequestViewData request, {
    required String action,
    required Future<void> Function(String idempotencyKey) operation,
  }) async {
    if (_busyRequestIds.contains(request.id)) {
      return;
    }
    setState(() => _busyRequestIds.add(request.id));
    final intentSlot = '$action:${request.id}';
    final idempotencyKey = _actionIntentKeys.putIfAbsent(
      intentSlot,
      () => const Uuid().v4(),
    );
    final startedAt = DateTime.now();
    Object? failure;
    try {
      await operation(idempotencyKey);
      _actionIntentKeys.remove(intentSlot);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'greeting',
              action: action,
              pageName: 'GreetingInboxPage',
              targetType: 'greeting_request',
              targetKey: request.id,
              payload: <String, Object?>{
                'result': 'success',
                'durationMs': DateTime.now()
                    .difference(startedAt)
                    .inMilliseconds,
              },
            ),
      );
    } catch (error) {
      failure = error;
      if (!mounted) {
        return;
      }
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'greeting',
              action: action,
              pageName: 'GreetingInboxPage',
              targetType: 'greeting_request',
              targetKey: request.id,
              payload: <String, Object?>{
                'result': 'failure',
                'durationMs': DateTime.now()
                    .difference(startedAt)
                    .inMilliseconds,
                'failReasonCode': error is CloudException
                    ? (error.code ?? error.runtimeFailure.code)
                    : error.runtimeType.toString(),
              },
            ),
      );
    } finally {
      if (mounted) {
        setState(() => _busyRequestIds.remove(request.id));
      }
    }
    if (failure == null || !mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: runtimeErrorSemantic(
        context,
        error: failure,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.dialog,
      ),
      onAction: (errorAction) async {
        if (errorAction.type == UiErrorActionType.retry ||
            errorAction.type == UiErrorActionType.resubmit) {
          await _runAction(request, action: action, operation: operation);
        }
      },
    );
  }

  Future<GreetingRequestViewData> _readbackReceived(
    String requestId, {
    required String expectedStatus,
  }) async {
    final items = await ref
        .read(greetingRepositoryProvider)
        .listInbox(status: '', limit: 100);
    return _requireConvergedRequest(
      items,
      requestId: requestId,
      expectedStatus: expectedStatus,
    );
  }

  Future<GreetingRequestViewData> _readbackSent(
    String requestId, {
    required String expectedStatus,
  }) async {
    final items = await ref
        .read(greetingRepositoryProvider)
        .listOutbox(status: '', limit: 100);
    return _requireConvergedRequest(
      items,
      requestId: requestId,
      expectedStatus: expectedStatus,
    );
  }

  GreetingRequestViewData _requireConvergedRequest(
    List<GreetingRequestViewData> items, {
    required String requestId,
    required String expectedStatus,
  }) {
    final matches = items
        .where((item) => item.id == requestId)
        .toList(growable: false);
    if (matches.length != 1 || matches.single.status != expectedStatus) {
      throw StateError(
        'GreetingRequest $requestId did not converge to $expectedStatus',
      );
    }
    return matches.single;
  }

  void _replaceReceived(GreetingRequestViewData updated) {
    if (!mounted) {
      return;
    }
    setState(() {
      _received = _replaceById(_received, updated);
    });
  }

  void _replaceSent(GreetingRequestViewData updated) {
    if (!mounted) {
      return;
    }
    setState(() {
      _sent = _replaceById(_sent, updated);
    });
  }

  List<GreetingRequestViewData> _replaceById(
    List<GreetingRequestViewData> source,
    GreetingRequestViewData updated,
  ) {
    return source
        .map((item) => item.id == updated.id ? updated : item)
        .toList(growable: false);
  }

  void _changeBox(_GreetingBox? next) {
    if (next == null || next == _box) {
      return;
    }
    setState(() => _box = next);
    unawaited(
      ref
          .read(journeyEventTrackerProvider)
          .trackAction(
            journey: 'greeting',
            action: 'switch_${next.name}_box',
            pageName: 'GreetingInboxPage',
          ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    return AppScaffold(
      backgroundColor: AppColors.iosPageBackground(context),
      navigationBar: AppNavigationBar(
        backgroundColor: AppColors.iosSystemBackground(context),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.back,
          onPressed: () {
            if (context.canPop()) {
              context.pop();
            } else {
              context.go(AppRoutePaths.chat);
            }
          },
        ),
        middle: Text(
          ChatText.chatGreetingCenterTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: Column(
        children: <Widget>[
          Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
              AppSpacing.containerMd,
              AppSpacing.intraGroupSm,
            ),
            child: SizedBox(
              width: double.infinity,
              child: CupertinoSlidingSegmentedControl<_GreetingBox>(
                groupValue: _box,
                children: const <_GreetingBox, Widget>{
                  _GreetingBox.received: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                    ),
                    child: Text(ChatText.chatGreetingReceived),
                  ),
                  _GreetingBox.sent: Padding(
                    padding: EdgeInsets.symmetric(
                      horizontal: AppSpacing.containerMd,
                    ),
                    child: Text(ChatText.chatGreetingSentTab),
                  ),
                },
                onValueChanged: _changeBox,
              ),
            ),
          ),
          Expanded(child: _buildContent(isDark)),
        ],
      ),
    );
  }

  Widget _buildContent(bool isDark) {
    if (_loading) {
      return AppRequestFeedback.section();
    }
    if (_rawError case final error?) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onRecovery: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load();
            return _rawError == null
                ? UiRecoveryOutcome.recovered
                : UiRecoveryOutcome.stillBlocked;
          }
          return UiRecoveryOutcome.cancelled;
        },
      );
    }
    final items = _box == _GreetingBox.received ? _received : _sent;
    if (items.isEmpty) {
      return AppEmptyState(
        icon: CupertinoIcons.chat_bubble_2,
        title: _box == _GreetingBox.received
            ? ChatText.chatGreetingReceivedEmpty
            : ChatText.chatGreetingSentEmpty,
      );
    }
    return CustomScrollView(
      slivers: <Widget>[
        CupertinoSliverRefreshControl(onRefresh: _load),
        SliverPadding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.intraGroupSm,
            AppSpacing.containerMd,
            AppSpacing.xl,
          ),
          sliver: SliverList.builder(
            itemCount: items.length,
            itemBuilder: (context, index) {
              final request = items[index];
              return Padding(
                padding: EdgeInsets.only(
                  bottom: index == items.length - 1
                      ? AppSpacing.zero
                      : AppSpacing.interGroupSm,
                ),
                child: _GreetingRequestCard(
                  request: request,
                  box: _box,
                  isDark: isDark,
                  busy: _busyRequestIds.contains(request.id),
                  onReply: () => _reply(request),
                  onIgnore: () => _ignore(request),
                  onCancel: () => _confirmCancel(request),
                  onOpenConversation: () {
                    final id = request.promotedConversationId?.trim() ?? '';
                    if (id.isNotEmpty) {
                      context.push(AppRoutePaths.chatDetail(id: id));
                    }
                  },
                ),
              );
            },
          ),
        ),
      ],
    );
  }
}
