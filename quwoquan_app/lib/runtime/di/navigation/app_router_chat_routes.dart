part of 'app_router.dart';

List<GoRoute> _chatRoutes(Ref ref) => <GoRoute>[
  GoRoute(
    path: AppRoutePaths.chatDetailPathTemplate.replaceAll('{id}', ':id'),
    pageBuilder: (context, state) {
      final id = state.pathParameters['id'] ?? '';
      final searchAnchorContext = state.extra is SearchConversationAnchorContext
          ? state.extra as SearchConversationAnchorContext
          : null;
      void handleBack() {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoutePaths.chat);
        }
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
      gatheringBoardRoute(),
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
            child: GroupManagePage(
              conversationId: id,
              conversationDissolver: ref.read(chatGroupAdminRepositoryProvider),
              assistantSkillPlacementPresenter: (context, request) =>
                  showAssistantSkillPlacementSheet(
                    context: context,
                    surfaceKind: request.surfaceKind,
                    surfaceId: request.surfaceId,
                  ),
            ),
          );
        },
      ),
      GoRoute(
        path: AppRoutePaths.chatTransferOwnershipSegment,
        pageBuilder: (context, state) {
          final id = state.pathParameters['id'] ?? '';
          return appRoutePage<void>(
            state: state,
            child: TransferOwnershipPage(
              conversationId: id,
              telemetryTracker: ref.read(
                chatInteractionTelemetryTrackerProvider,
              ),
            ),
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
