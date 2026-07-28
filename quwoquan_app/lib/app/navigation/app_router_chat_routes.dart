part of 'app_router.dart';

List<GoRoute> _chatRoutes(Ref ref) => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
    pageBuilder: (context, state) {
      final id = state.pathParameters['id'] ?? '';
      final assistantOpenContext = state.extra is AssistantOpenContext
          ? state.extra as AssistantOpenContext
          : null;
      final searchAnchorContext = state.extra is SearchConversationAnchorContext
          ? state.extra as SearchConversationAnchorContext
          : null;
      final isAssistant = id == AppConceptConstants.assistantConversationId;
      void handleBack() {
        if (context.canPop()) {
          context.pop();
        } else if (isAssistant) {
          final lastTab = ref.read(lastMainTabBeforeAssistantProvider);
          ref.read(lastMainTabBeforeAssistantProvider.notifier).set(null);
          final route = lastTab?.routePath ?? AppRoutePaths.chat;
          context.go(route);
        } else {
          context.go(AppRoutePaths.chat);
        }
      }

      if (isAssistant) {
        return appRoutePage<void>(
          state: state,
          child: PersonalAssistantConversationPage(
            onBack: handleBack,
            assistantOpenContext: assistantOpenContext,
          ),
        );
      }
      return appRoutePage<void>(
        state: state,
        child: ChatConversationPage(
          conversationId: id,
          onBack: handleBack,
          searchAnchorContext: searchAnchorContext,
        ),
      );
    },
    routes: <RouteBase>[
      GoRoute(
        path: AppRoutePaths.chatSettingsSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: ChatSettingsPage(conversationId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatMemberSearchSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: GroupMemberSearchPage(conversationId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatAnnouncementSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: ChatAnnouncementPage(conversationId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatAddMembersSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: StartGroupChatPage(
              conversationId: id,
              onBack: () {
                if (context.canPop()) {
                  context.pop();
                } else {
                  context.go(AppRoutePaths.chat);
                }
              },
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatManageSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: GroupManagePage(conversationId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatTransferOwnershipSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: TransferOwnershipPage(conversationId: id),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatAdminsSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: GroupAdminsPage(conversationId: id),
          );
        },
      ),
    ],
  ),
];
