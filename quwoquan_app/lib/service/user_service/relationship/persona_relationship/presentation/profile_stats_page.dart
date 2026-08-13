import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/content_service/content/content_behavior_fact/application/public/content_behavior_repository.dart'
    show ReferralSource;
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/design_system/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/design_system/navigation/tab_navigation.dart';
import 'package:quwoquan_app/design_system/search/embedded/embedded_member_search_bar_plain.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/user_profile_route_extra.dart';
import 'package:quwoquan_app/runtime/observability/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/runtime/observability/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/design_system/media/app_cached_network_image.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_list_page_semantics.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/surfaces/app_action_sheet.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_gate.dart';
import 'package:quwoquan_app/runtime/di/app_providers_chat_search.dart'
    show
        chatConversationRepositoryProvider,
        journeyEventTrackerProvider,
        relationshipCapabilityRepositoryForSurfaceProvider;
import 'package:quwoquan_app/runtime/di/app_providers_circle_facets.dart'
    show userProfileCircleMembershipQueryProvider;
import 'package:quwoquan_app/runtime/di/app_providers_operations.dart'
    show
        personaRelationshipCommandWriterProvider,
        personaRelationshipQueryProvider,
        profileQueryProvider;
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart'
    show userRelationshipStateProvider;
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_detail_page_route_extra.dart';

part 'profile_stats_page_widgets.dart';
part 'profile_stats_page_actions.dart';

/// 主页统计详情页（粉丝 / 关注 / 圈子）。
///
/// 路由：`/profile/stats?type=fans|following|circles&userId=...`
class ProfileStatsPage extends ConsumerStatefulWidget {
  const ProfileStatsPage({super.key, this.type = 'fans', this.userId = ''});

  final String type;
  final String userId;

  @override
  ConsumerState<ProfileStatsPage> createState() => _ProfileStatsPageState();
}

enum _ProfileStatsTab { fans, following, circles }

extension on _ProfileStatsTab {
  String get routeValue => switch (this) {
    _ProfileStatsTab.fans => 'fans',
    _ProfileStatsTab.following => 'following',
    _ProfileStatsTab.circles => 'circles',
  };

  String get label => switch (this) {
    _ProfileStatsTab.fans => CommunityText.circleFans,
    _ProfileStatsTab.following => FoundationText.follow,
    _ProfileStatsTab.circles => ChatText.contactsTabCircles,
  };

  String get searchHint => switch (this) {
    _ProfileStatsTab.fans => CommunityText.searchFansHint,
    _ProfileStatsTab.following => ProfileText.profileStatsSearchFollowingHint,
    _ProfileStatsTab.circles => ContactText.searchCircleHint,
  };

  String get analyticsPageName => 'profile_stats_$routeValue';
}

class _ProfileStatsTabMemory {
  _ProfileStatsTabMemory({
    required this.searchController,
    required this.scrollController,
  });

  final TextEditingController searchController;
  final ScrollController scrollController;
  Timer? searchDebounce;
  List<Object> items = <Object>[];
  String? nextCursor;
  int? totalCount;
  Object? loadError;
  Object? refreshError;
  Object? appendError;
  bool hasLoaded = false;
  bool isLoading = false;
  bool isRefreshing = false;
  bool isAppending = false;
  String lastSubmittedQuery = '';
  int requestGeneration = 0;

  String get query => searchController.text.trim();
  bool get hasMore => (nextCursor ?? '').trim().isNotEmpty;

  void reset({bool clearQuery = false}) {
    requestGeneration += 1;
    searchDebounce?.cancel();
    if (clearQuery) {
      searchController.clear();
      lastSubmittedQuery = '';
    }
    items = <Object>[];
    nextCursor = null;
    totalCount = null;
    loadError = null;
    refreshError = null;
    appendError = null;
    hasLoaded = false;
    isLoading = false;
    isRefreshing = false;
    isAppending = false;
    if (scrollController.hasClients) {
      scrollController.jumpTo(0);
    }
  }

  void dispose() {
    searchDebounce?.cancel();
    searchController.dispose();
    scrollController.dispose();
  }
}

class _ProfileStatsPageState extends ConsumerState<ProfileStatsPage> {
  static const int _pageSize = PersonaRelationshipListQuery.defaultLimit;

  late _ProfileStatsTab _activeTab;
  late final Map<_ProfileStatsTab, _ProfileStatsTabMemory> _tabMemories;
  late final JourneyEventTracker _journeyTracker;

  UserHomepageBundleViewData? _bundle;
  Object? _bundleError;
  bool _isBundleLoading = true;
  bool _suspendSearchCallbacks = false;
  bool _didTrackExposure = false;
  bool _didTrackPrivacyIntercept = false;
  int _bundleRequestGeneration = 0;
  int _relationshipAttemptGeneration = 0;
  final Set<String> _pendingRelationshipTargets = <String>{};
  final Set<String> _pendingConversationTargets = <String>{};

  String get _userId => widget.userId.trim();
  _ProfileStatsTabMemory get _activeMemory => _tabMemories[_activeTab]!;
  bool get _isBlockedProfile =>
      _bundle?.relationshipCapability?.isBlocked == true ||
      _bundle?.relationshipCapability?.isBlockedBy == true ||
      _bundle?.viewerContext.relationToTarget == 'blocked' ||
      _bundle?.viewerContext.relationToTarget == 'restricted';

  @override
  void initState() {
    super.initState();
    _journeyTracker = ref.read(journeyEventTrackerProvider);
    _activeTab = _normalizeTab(widget.type);
    _tabMemories = {
      for (final tab in _ProfileStatsTab.values) tab: _createTabMemory(tab),
    };
    _loadBundleAndActiveTab();
  }

  @override
  void didUpdateWidget(covariant ProfileStatsPage oldWidget) {
    super.didUpdateWidget(oldWidget);
    final nextTab = _normalizeTab(widget.type);
    if (oldWidget.userId != widget.userId) {
      _activeTab = nextTab;
      _resetTabMemories(clearQuery: true);
      _bundle = null;
      _bundleError = null;
      _isBundleLoading = true;
      _didTrackExposure = false;
      _didTrackPrivacyIntercept = false;
      _loadBundleAndActiveTab();
      return;
    }
    if (nextTab != _activeTab) {
      _selectTab(nextTab, trackEvent: false);
    }
  }

  @override
  void dispose() {
    for (final memory in _tabMemories.values) {
      memory.dispose();
    }
    super.dispose();
  }

  _ProfileStatsTabMemory _createTabMemory(_ProfileStatsTab tab) {
    final memory = _ProfileStatsTabMemory(
      searchController: TextEditingController(),
      scrollController: ScrollController(),
    );
    memory.searchController.addListener(() => _handleSearchChanged(tab));
    memory.scrollController.addListener(() => _maybeAppend(tab));
    return memory;
  }

  static _ProfileStatsTab _normalizeTab(String raw) {
    switch (raw) {
      case 'following':
        return _ProfileStatsTab.following;
      case 'circles':
        return _ProfileStatsTab.circles;
      case 'fans':
      default:
        return _ProfileStatsTab.fans;
    }
  }

  void _resetTabMemories({required bool clearQuery}) {
    _suspendSearchCallbacks = true;
    for (final memory in _tabMemories.values) {
      memory.reset(clearQuery: clearQuery);
    }
    _suspendSearchCallbacks = false;
  }

  void _commitState(VoidCallback mutation) {
    if (mounted) {
      setState(mutation);
    }
  }

  Future<void> _loadBundleAndActiveTab() async {
    final request = ++_bundleRequestGeneration;
    final requestedUserId = _userId;
    if (_userId.isEmpty) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isBundleLoading = false;
        _bundle = null;
        _bundleError = null;
      });
      return;
    }
    setState(() {
      _isBundleLoading = true;
      _bundleError = null;
    });
    _recordPageState(
      tab: _activeTab,
      phase: 'onlineLoading',
      source: 'online',
      itemCount: _activeMemory.items.length,
      hasCache: _bundle != null,
    );
    try {
      final bundle = await ref
          .read(profileQueryProvider(AppUiSurfaces.profileStats))
          .getUserHomepageBundle(requestedUserId);
      if (!mounted ||
          request != _bundleRequestGeneration ||
          requestedUserId != _userId) {
        return;
      }
      setState(() {
        _bundle = bundle;
        _bundleError = null;
        _isBundleLoading = false;
      });
      _recordPageState(
        tab: _activeTab,
        phase: 'onlineSuccess',
        source: 'online',
      );
      _trackExposureIfNeeded(bundle);
      if (!bundle.viewerContext.canViewFullProfile) {
        _trackPrivacyInterceptIfNeeded(bundle);
        return;
      }
      await _ensureTabLoaded(_activeTab, forceReload: true);
    } catch (error) {
      if (!mounted ||
          request != _bundleRequestGeneration ||
          requestedUserId != _userId) {
        return;
      }
      setState(() {
        _bundleError = error;
        _isBundleLoading = false;
      });
      _recordPageState(
        tab: _activeTab,
        phase: 'blockingFailure',
        source: 'online',
        error: error,
      );
    }
  }

  Future<void> _ensureTabLoaded(
    _ProfileStatsTab tab, {
    bool forceReload = false,
  }) async {
    if (_bundle == null || !_bundle!.viewerContext.canViewFullProfile) {
      return;
    }
    final memory = _tabMemories[tab]!;
    if (memory.hasLoaded && !forceReload) {
      return;
    }
    await _loadTab(tab);
  }

  void _handleSearchChanged(_ProfileStatsTab tab) {
    if (_suspendSearchCallbacks) {
      return;
    }
    final memory = _tabMemories[tab]!;
    memory.searchDebounce?.cancel();
    memory.searchDebounce = Timer(const Duration(milliseconds: 280), () {
      if (!mounted) {
        return;
      }
      final query = memory.query;
      if (query == memory.lastSubmittedQuery && memory.hasLoaded) {
        return;
      }
      _trackSearchInteraction(
        tab,
        query,
        previousQuery: memory.lastSubmittedQuery,
      );
      memory.lastSubmittedQuery = query;
      unawaited(_loadTab(tab));
    });
  }

  Future<void> _loadTab(_ProfileStatsTab tab) async {
    final memory = _tabMemories[tab]!;
    final request = ++memory.requestGeneration;
    final requestedUserId = _userId;
    final hadItems = memory.items.isNotEmpty;
    setState(() {
      memory.isLoading = true;
      memory.isRefreshing = false;
      memory.isAppending = false;
      memory.loadError = null;
      memory.refreshError = null;
      memory.appendError = null;
      memory.nextCursor = null;
      if (!hadItems) {
        memory.items = <Object>[];
      }
    });
    final query = memory.query;
    try {
      final page = await _fetchTabPage(
        tab,
        query: query.isEmpty ? null : query,
      );
      if (!mounted ||
          request != memory.requestGeneration ||
          requestedUserId != _userId ||
          query != memory.query) {
        return;
      }
      setState(() {
        memory.items = page.items;
        memory.nextCursor = page.nextCursor;
        memory.totalCount = page.totalCount;
        memory.hasLoaded = true;
        memory.isLoading = false;
        memory.loadError = null;
        memory.appendError = null;
      });
      _recordPageState(
        tab: tab,
        phase: 'onlineSuccess',
        source: 'online',
        itemCount: page.items.length,
      );
    } catch (error) {
      if (!mounted ||
          request != memory.requestGeneration ||
          requestedUserId != _userId ||
          query != memory.query) {
        return;
      }
      setState(() {
        memory.isLoading = false;
        memory.loadError = error;
      });
      _recordPageState(
        tab: tab,
        phase: 'blockingFailure',
        source: hadItems ? 'retained' : 'online',
        error: error,
        itemCount: memory.items.length,
      );
    }
  }

  Future<void> _refreshActiveTab() async {
    final tab = _activeTab;
    final memory = _activeMemory;
    if (_bundle == null || !_bundle!.viewerContext.canViewFullProfile) {
      return;
    }
    final request = ++memory.requestGeneration;
    final requestedUserId = _userId;
    final query = memory.query;
    setState(() {
      memory.isRefreshing = true;
      memory.isAppending = false;
      memory.appendError = null;
      memory.loadError = null;
      memory.refreshError = null;
    });
    try {
      final page = await _fetchTabPage(
        tab,
        query: query.isEmpty ? null : query,
      );
      if (!mounted ||
          request != memory.requestGeneration ||
          requestedUserId != _userId ||
          query != memory.query) {
        return;
      }
      setState(() {
        memory.items = page.items;
        memory.nextCursor = page.nextCursor;
        memory.totalCount = page.totalCount;
        memory.hasLoaded = true;
        memory.isRefreshing = false;
      });
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordRefresh(
            pageName: tab.analyticsPageName,
            result: 'success',
            retained: false,
            itemCount: page.items.length,
          );
    } catch (error) {
      if (!mounted ||
          request != memory.requestGeneration ||
          requestedUserId != _userId ||
          query != memory.query) {
        return;
      }
      setState(() {
        memory.isRefreshing = false;
        memory.refreshError = error;
      });
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordRefresh(
            pageName: tab.analyticsPageName,
            result: 'failed',
            retained: memory.items.isNotEmpty,
            error: error,
            itemCount: memory.items.length,
          );
    }
  }

  void _maybeAppend(_ProfileStatsTab tab) {
    final memory = _tabMemories[tab]!;
    if (tab != _activeTab ||
        !memory.hasLoaded ||
        memory.isLoading ||
        memory.isRefreshing ||
        memory.isAppending ||
        !memory.hasMore ||
        !memory.scrollController.hasClients) {
      return;
    }
    final position = memory.scrollController.position;
    if (position.extentAfter > 320) {
      return;
    }
    unawaited(_appendTab(tab));
  }

  Future<void> _appendTab(_ProfileStatsTab tab) async {
    final memory = _tabMemories[tab]!;
    final cursor = memory.nextCursor;
    if ((cursor ?? '').trim().isEmpty) {
      return;
    }
    final request = ++memory.requestGeneration;
    final requestedUserId = _userId;
    final query = memory.query;
    final itemCountBefore = memory.items.length;
    setState(() {
      memory.isAppending = true;
      memory.appendError = null;
    });
    try {
      final page = await _fetchTabPage(
        tab,
        query: query.isEmpty ? null : query,
        cursor: cursor,
      );
      if (!mounted ||
          request != memory.requestGeneration ||
          requestedUserId != _userId ||
          query != memory.query ||
          cursor != memory.nextCursor) {
        return;
      }
      if ((page.nextCursor ?? '').trim().isNotEmpty &&
          page.nextCursor!.trim() == cursor!.trim()) {
        throw StateError('Profile stats cursor did not advance');
      }
      final merged = _mergeItems(tab, memory.items, page.items);
      setState(() {
        memory.items = merged;
        memory.nextCursor = page.nextCursor;
        memory.totalCount = page.totalCount ?? memory.totalCount;
        memory.isAppending = false;
      });
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordAppend(
            pageName: tab.analyticsPageName,
            result: 'success',
            cursorPresent: true,
            hasMore: (page.nextCursor ?? '').trim().isNotEmpty,
            itemCountBefore: itemCountBefore,
            itemCountAfter: merged.length,
          );
      _trackAction(
        'append_succeeded',
        targetType: 'tab',
        targetKey: tab.routeValue,
        payload: <String, Object?>{
          'tab': tab.routeValue,
          'surfaceId': 'profile_stats',
          'itemCountAfter': merged.length,
          'nextCursorPresent': (page.nextCursor ?? '').trim().isNotEmpty,
        },
      );
    } catch (error) {
      if (!mounted ||
          request != memory.requestGeneration ||
          requestedUserId != _userId ||
          query != memory.query ||
          cursor != memory.nextCursor) {
        return;
      }
      setState(() {
        memory.isAppending = false;
        memory.appendError = error;
      });
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordAppend(
            pageName: tab.analyticsPageName,
            result: 'failed',
            cursorPresent: true,
            hasMore: memory.hasMore,
            itemCountBefore: itemCountBefore,
            itemCountAfter: itemCountBefore,
            error: error,
          );
      _trackAction(
        'append_failed',
        targetType: 'tab',
        targetKey: tab.routeValue,
        payload: <String, Object?>{
          'tab': tab.routeValue,
          'surfaceId': 'profile_stats',
          'error': runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.listAppend,
            scope: UiErrorScope.section,
          ).message,
        },
      );
    }
  }

  Future<CursorPage<Object>> _fetchTabPage(
    _ProfileStatsTab tab, {
    String? query,
    String? cursor,
  }) async {
    final relationshipQuery = ref.read(
      personaRelationshipQueryProvider(AppUiSurfaces.profileStats),
    );
    switch (tab) {
      case _ProfileStatsTab.circles:
        final page = await ref
            .read(userProfileCircleMembershipQueryProvider)
            .listPersonaCircles(
              PersonaCircleListQuery(
                personaId: _userId,
                query: query,
                cursor: cursor,
                limit: _pageSize,
              ),
            );
        final items = page.items;
        return CursorPage<Object>(
          items: items.cast<Object>(),
          nextCursor: page.cursor,
        );
      case _ProfileStatsTab.following:
        final page = await relationshipQuery.listFollowing(
          personaId: _userId,
          query: query,
          cursor: cursor,
          limit: _pageSize,
        );
        return CursorPage<Object>(
          items: page.items.cast<Object>(),
          nextCursor: page.nextCursor,
          totalCount: page.totalCount,
        );
      case _ProfileStatsTab.fans:
        final page = await relationshipQuery.listFollowers(
          personaId: _userId,
          query: query,
          cursor: cursor,
          limit: _pageSize,
        );
        return CursorPage<Object>(
          items: page.items.cast<Object>(),
          nextCursor: page.nextCursor,
          totalCount: page.totalCount,
        );
    }
  }

  List<Object> _mergeItems(
    _ProfileStatsTab tab,
    List<Object> existing,
    List<Object> incoming,
  ) {
    final seenKeys = existing.map((item) => _itemKey(tab, item)).toSet();
    final merged = List<Object>.from(existing);
    for (final item in incoming) {
      final key = _itemKey(tab, item);
      if (!seenKeys.add(key)) {
        continue;
      }
      merged.add(item);
    }
    return merged;
  }

  String _itemKey(_ProfileStatsTab tab, Object item) {
    return switch (tab) {
      _ProfileStatsTab.circles => (item as PersonaCircleSlice).circleId,
      _ProfileStatsTab.fans || _ProfileStatsTab.following =>
        (item as ProfileSocialRelationRowViewData).personaId,
    };
  }

  void _selectTab(_ProfileStatsTab nextTab, {required bool trackEvent}) {
    if (nextTab == _activeTab) {
      return;
    }
    setState(() => _activeTab = nextTab);
    if (trackEvent) {
      _trackAction(
        'tab_switch',
        targetType: 'tab',
        targetKey: nextTab.routeValue,
        payload: <String, Object?>{
          'tab': nextTab.routeValue,
          'surfaceId': 'profile_stats',
        },
      );
    }
    unawaited(_ensureTabLoaded(nextTab));
  }

  void _trackExposureIfNeeded(UserHomepageBundleViewData bundle) {
    if (_didTrackExposure) {
      return;
    }
    _didTrackExposure = true;
    _trackAction(
      'exposure',
      targetType: 'profile_stats',
      targetKey: _userId,
      payload: <String, Object?>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
        'isOwner': bundle.viewerContext.isOwner,
        'isGuest': bundle.viewerContext.isGuest,
      },
    );
  }

  void _trackPrivacyInterceptIfNeeded(UserHomepageBundleViewData bundle) {
    if (_didTrackPrivacyIntercept) {
      return;
    }
    _didTrackPrivacyIntercept = true;
    _trackAction(
      'privacy_intercept_exposure',
      targetType: 'profile_stats',
      targetKey: _userId,
      payload: <String, Object?>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
        'relationToTarget': bundle.viewerContext.relationToTarget,
        'blocked':
            bundle.relationshipCapability?.isBlocked == true ||
            bundle.relationshipCapability?.isBlockedBy == true,
      },
    );
  }

  void _trackSearchInteraction(
    _ProfileStatsTab tab,
    String query, {
    required String previousQuery,
  }) {
    if (query.isEmpty && previousQuery.isNotEmpty) {
      _trackAction(
        'search_clear',
        targetType: 'tab',
        targetKey: tab.routeValue,
        payload: <String, Object?>{
          'tab': tab.routeValue,
          'surfaceId': 'profile_stats',
        },
      );
      return;
    }
    if (query.isNotEmpty) {
      _trackAction(
        'search_submit',
        targetType: 'tab',
        targetKey: tab.routeValue,
        payload: <String, Object?>{
          'tab': tab.routeValue,
          'surfaceId': 'profile_stats',
          'queryLength': query.length,
        },
      );
    }
  }

  void _trackAction(
    String action, {
    String targetType = '',
    String targetKey = '',
    String entityType = 'user_profile',
    String entityId = '',
    Map<String, Object?> payload = const <String, Object?>{},
  }) {
    unawaited(
      _journeyTracker.trackAction(
        journey: 'profile_stats',
        action: action,
        pageName: 'profile_stats',
        targetType: targetType,
        targetKey: targetKey,
        entityType: entityType,
        entityId: entityId.isNotEmpty ? entityId : _userId,
        payload: payload,
      ),
    );
  }

  void _recordPageState({
    required _ProfileStatsTab tab,
    required String phase,
    required String source,
    Object? error,
    int? itemCount,
    bool? hasCache,
  }) {
    ref
        .read(pageLifecycleObservabilityProvider)
        .recordPageState(
          pageName: tab.analyticsPageName,
          route: AppRoutePaths.profileStats(),
          surface: 'profile_stats',
          phase: phase,
          source: source,
          error: error,
          itemCount: itemCount,
          hasCache: hasCache,
        );
  }

  void _openUserProfile(ProfileSocialRelationRowViewData row) {
    _trackAction(
      'row_click',
      targetType: 'profile',
      targetKey: row.personaId,
      payload: <String, Object?>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
      },
    );
    context.push(
      AppRoutePaths.userProfile(userHandle: row.personaId),
      extra: UserProfileRouteExtra(
        personaId: row.personaId,
        avatarUrl: row.avatarUrl.isNotEmpty ? row.avatarUrl : null,
        displayName: row.displayName.isNotEmpty ? row.displayName : null,
      ),
    );
  }

  void _openCircle(PersonaCircleSlice circle) {
    _trackAction(
      'row_click',
      targetType: 'circle',
      targetKey: circle.circleId,
      entityType: 'circle',
      entityId: circle.circleId,
      payload: <String, Object?>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
      },
    );
    context.push(
      AppRoutePaths.circleDetail(id: circle.circleId),
      extra: const CircleDetailPageRouteExtra(
        referralSource: ReferralSource.authorProfile,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final body = _buildBody(context, isDark);
    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: '',
      middle: _buildPrimaryTabBar(context),
      onBack: () => context.pop(),
      body: body,
    );
  }
}
