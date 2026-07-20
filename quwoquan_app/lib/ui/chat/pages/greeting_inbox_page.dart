import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/services/user/greeting_repository.dart';
import 'package:quwoquan_app/core/constants/chat_text_constants.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/chat/providers/greeting_inbox_provider.dart';

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
  List<GreetingRequestDto> _received = const <GreetingRequestDto>[];
  List<GreetingRequestDto> _sent = const <GreetingRequestDto>[];
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
      final results = await Future.wait<List<GreetingRequestDto>>(
        <Future<List<GreetingRequestDto>>>[
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

  Future<void> _reply(GreetingRequestDto request) async {
    await _runAction(
      request,
      action: 'reply_greeting',
      operation: () async {
        final result = await ref
            .read(greetingRepositoryProvider)
            .replyGreeting(request.id);
        final now = DateTime.now().toUtc();
        _replaceReceived(
          request.copyWith(
            status: 'replied',
            promotedConversationId: result.conversationId,
            decisionAt: now,
            updatedAt: now,
          ),
        );
        ref.invalidate(chatGreetingInboxProvider);
        if (!mounted) {
          return;
        }
        AppToast.show(context, ChatText.chatGreetingReplySucceeded);
        final conversationId = result.conversationId.trim();
        if (conversationId.isNotEmpty) {
          context.push(AppRoutePaths.chatDetail(id: conversationId));
        }
      },
    );
  }

  Future<void> _ignore(GreetingRequestDto request) async {
    await _runAction(
      request,
      action: 'ignore_greeting',
      operation: () async {
        final updated = await ref
            .read(greetingRepositoryProvider)
            .ignoreGreeting(request.id);
        _replaceReceived(updated);
        ref.invalidate(chatGreetingInboxProvider);
        if (mounted) {
          AppToast.show(context, ChatText.chatGreetingIgnored);
        }
      },
    );
  }

  Future<void> _confirmCancel(GreetingRequestDto request) async {
    final confirmed = await showAppCupertinoDialog<bool>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: const Text(ChatText.chatGreetingCancelConfirmTitle),
        content: const Text(ChatText.chatGreetingCancelConfirmMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text(UITextConstants.cancel),
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
      operation: () async {
        final updated = await ref
            .read(greetingRepositoryProvider)
            .cancelGreeting(request.id);
        _replaceSent(updated);
        if (mounted) {
          AppToast.show(context, ChatText.chatGreetingCancelled);
        }
      },
    );
  }

  Future<void> _runAction(
    GreetingRequestDto request, {
    required String action,
    required Future<void> Function() operation,
  }) async {
    if (_busyRequestIds.contains(request.id)) {
      return;
    }
    setState(() => _busyRequestIds.add(request.id));
    final startedAt = DateTime.now();
    try {
      await operation();
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'greeting',
              action: action,
              pageName: 'GreetingInboxPage',
              targetType: 'greeting_request',
              targetKey: request.id,
              payload: <String, dynamic>{
                'result': 'success',
                'durationMs': DateTime.now()
                    .difference(startedAt)
                    .inMilliseconds,
              },
            ),
      );
    } catch (error) {
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
              payload: <String, dynamic>{
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
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error,
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
    } finally {
      if (mounted) {
        setState(() => _busyRequestIds.remove(request.id));
      }
    }
  }

  void _replaceReceived(GreetingRequestDto updated) {
    if (!mounted) {
      return;
    }
    setState(() {
      _received = _replaceById(_received, updated);
    });
  }

  void _replaceSent(GreetingRequestDto updated) {
    if (!mounted) {
      return;
    }
    setState(() {
      _sent = _replaceById(_sent, updated);
    });
  }

  List<GreetingRequestDto> _replaceById(
    List<GreetingRequestDto> source,
    GreetingRequestDto updated,
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
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_rawError case final error?) {
      return AppPageErrorState(
        semantic: runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        ),
        onAction: (action) async {
          if (action.type == UiErrorActionType.retry) {
            await _load();
          }
        },
      );
    }
    final items = _box == _GreetingBox.received ? _received : _sent;
    if (items.isEmpty) {
      return _GreetingEmptyState(box: _box, isDark: isDark);
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
