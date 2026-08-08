import "package:quwoquan_cloud_contracts/generated/chat_contracts.dart";
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/service/chat_service/chat/message/application/public/message_home_rows.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

final messageHomeRowsStateProvider =
    FutureProvider.family<MessageHomeRowsSnapshot, String>((ref, filter) async {
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordPageState(
            pageName: 'chat_list',
            route: '/chat',
            surface: filter,
            phase: 'onlineLoading',
            source: 'online',
          );
      final repo = ref.watch(chatConversationRepositoryProvider);
      try {
        final rows = await repo.listMessageHome(filter: filter, limit: 100);
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'chat_list',
              route: '/chat',
              surface: filter,
              phase: 'onlineSuccess',
              source: 'online',
              itemCount: rows.length,
              hasCache: false,
            );
        return MessageHomeRowsSnapshot(
          rows: List<MessageHomeRow>.unmodifiable(rows),
        );
      } catch (error) {
        ref
            .read(pageLifecycleObservabilityProvider)
            .recordPageState(
              pageName: 'chat_list',
              route: '/chat',
              surface: filter,
              phase: 'blockingFailure',
              source: 'online',
              error: error,
              copyKey: 'chatListLoadFailedTitle',
              itemCount: 0,
              hasCache: false,
            );
        rethrow;
      }
    });
