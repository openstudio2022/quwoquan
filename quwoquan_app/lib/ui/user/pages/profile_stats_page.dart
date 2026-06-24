import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/cloud_api_defaults.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/cursor_page.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/cloud/services/user/relationship_capability_repository.dart';
import 'package:quwoquan_app/components/search/embedded/embedded_member_search_bar_plain.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/trackers/journey_event_tracker.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

part 'profile_stats_page_widgets.dart';

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
    _ProfileStatsTab.fans => UITextConstants.circleFans,
    _ProfileStatsTab.following => UITextConstants.follow,
    _ProfileStatsTab.circles => UITextConstants.contactsTabCircles,
  };

  String get searchHint => switch (this) {
    _ProfileStatsTab.fans => UITextConstants.searchFansHint,
    _ProfileStatsTab.following =>
      UITextConstants.profileStatsSearchFollowingHint,
    _ProfileStatsTab.circles => UITextConstants.searchCircleHint,
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
  Object? appendError;
  bool hasLoaded = false;
  bool isLoading = false;
  bool isRefreshing = false;
  bool isAppending = false;
  String lastSubmittedQuery = '';

  String get query => searchController.text.trim();
  bool get hasMore => (nextCursor ?? '').trim().isNotEmpty;

  void reset({bool clearQuery = false}) {
    searchDebounce?.cancel();
    if (clearQuery) {
      searchController.clear();
      lastSubmittedQuery = '';
    }
    items = <Object>[];
    nextCursor = null;
    totalCount = null;
    loadError = null;
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
  static const int _pageSize = CloudApiDefaults.pageLimit;

  late _ProfileStatsTab _activeTab;
  late final Map<_ProfileStatsTab, _ProfileStatsTabMemory> _tabMemories;
  late final JourneyEventTracker _journeyTracker;

  UserHomepageBundleViewData? _bundle;
  Object? _bundleError;
  bool _isBundleLoading = true;
  bool _suspendSearchCallbacks = false;
  bool _didTrackExposure = false;
  bool _didTrackPrivacyIntercept = false;

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

  Future<void> _loadBundleAndActiveTab() async {
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
          .read(userProfileRepositoryProvider)
          .getUserHomepageBundle(_userId);
      if (!mounted) {
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
      if (!mounted) {
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
    final hadItems = memory.items.isNotEmpty;
    setState(() {
      memory.isLoading = true;
      memory.isRefreshing = false;
      memory.isAppending = false;
      memory.loadError = null;
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
      if (!mounted) {
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
      if (!mounted) {
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
    final memory = _activeMemory;
    if (_bundle == null || !_bundle!.viewerContext.canViewFullProfile) {
      return;
    }
    setState(() {
      memory.isRefreshing = true;
      memory.appendError = null;
      memory.loadError = null;
    });
    try {
      final page = await _fetchTabPage(
        _activeTab,
        query: memory.query.isEmpty ? null : memory.query,
      );
      if (!mounted) {
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
            pageName: _activeTab.analyticsPageName,
            result: 'success',
            retained: false,
            itemCount: page.items.length,
          );
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() => memory.isRefreshing = false);
      ref
          .read(pageLifecycleObservabilityProvider)
          .recordRefresh(
            pageName: _activeTab.analyticsPageName,
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
    final itemCountBefore = memory.items.length;
    setState(() {
      memory.isAppending = true;
      memory.appendError = null;
    });
    try {
      final page = await _fetchTabPage(
        tab,
        query: memory.query.isEmpty ? null : memory.query,
        cursor: cursor,
      );
      if (!mounted) {
        return;
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
        payload: <String, dynamic>{
          'tab': tab.routeValue,
          'surfaceId': 'profile_stats',
          'itemCountAfter': merged.length,
          'nextCursorPresent': (page.nextCursor ?? '').trim().isNotEmpty,
        },
      );
    } catch (error) {
      if (!mounted) {
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
        payload: <String, dynamic>{
          'tab': tab.routeValue,
          'surfaceId': 'profile_stats',
          'error': runtimeErrorDisplayMessage(error),
        },
      );
    }
  }

  Future<CursorPage<Object>> _fetchTabPage(
    _ProfileStatsTab tab, {
    String? query,
    String? cursor,
  }) async {
    final repo = ref.read(userProfileRepositoryProvider);
    switch (tab) {
      case _ProfileStatsTab.circles:
        final page = await repo.listUserCirclesPage(
          _userId,
          query: query,
          cursor: cursor,
          limit: _pageSize,
        );
        return CursorPage<Object>(
          items: page.items.cast<Object>(),
          nextCursor: page.nextCursor,
          totalCount: page.totalCount,
        );
      case _ProfileStatsTab.following:
        final page = await repo.listFollowingPage(
          _userId,
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
        final page = await repo.listFollowersPage(
          _userId,
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
      _ProfileStatsTab.circles => (item as CircleDto).id,
      _ProfileStatsTab.fans || _ProfileStatsTab.following =>
        (item as ProfileSocialRelationRowViewData).subAccountId,
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
        payload: <String, dynamic>{
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
      payload: <String, dynamic>{
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
      payload: <String, dynamic>{
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
        payload: <String, dynamic>{
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
        payload: <String, dynamic>{
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
    Map<String, dynamic> payload = const <String, dynamic>{},
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
          route: '/profile/stats',
          surface: 'profile_stats',
          phase: phase,
          source: source,
          error: error,
          itemCount: itemCount,
          hasCache: hasCache,
        );
  }

  RelationshipCapabilityDto _resolvedCapability(
    ProfileSocialRelationRowViewData row,
  ) {
    final base = row.effectiveRelationshipCapability;
    final relationshipState = ref.read(userRelationshipStateProvider);
    final targetId = row.subAccountId;
    if (base == null) {
      final sharedFollowing =
          relationshipState.hasRelationshipStateFor(targetId)
          ? relationshipState.isFollowing(targetId)
          : false;
      return RelationshipCapabilityDto.fromFollowFlags(
        viewerId: '',
        targetId: targetId,
        isFollowing: sharedFollowing,
        isFollowedBy:
            row.relationState == 'followed_by' || row.relationState == 'mutual',
        isSelf: row.relationState == 'self',
      );
    }
    if (!relationshipState.hasRelationshipStateFor(targetId)) {
      return base;
    }
    final sharedFollowing = relationshipState.isFollowing(targetId);
    if (sharedFollowing == base.viewerFollowsTarget) {
      return base;
    }
    return RelationshipCapabilityDto.fromFollowFlags(
      viewerId: base.viewerSubAccountId,
      targetId: base.targetSubAccountId.isNotEmpty
          ? base.targetSubAccountId
          : targetId,
      isFollowing: sharedFollowing,
      isFollowedBy: base.targetFollowsViewer,
      isSelf: base.isSelf,
      isBlocked: base.isBlocked,
      isBlockedBy: base.isBlockedBy,
      hasFormalConversation: base.hasFormalConversation,
      hasPendingGreeting: base.hasPendingGreeting,
    );
  }

  Future<void> _handleFollowAction(ProfileSocialRelationRowViewData row) async {
    final capability = _resolvedCapability(row);
    if (capability.isSelf || capability.isBlocked || capability.isBlockedBy) {
      return;
    }
    _trackAction(
      'follow_click',
      targetType: 'profile',
      targetKey: row.subAccountId,
      payload: <String, dynamic>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
        'relationState': capability.relationState,
      },
    );
    if (!await requireLogin(ref, context, AuthGateReason.follow)) {
      return;
    }
    final currentFollowing = capability.viewerFollowsTarget;
    ref
        .read(userRelationshipStateProvider.notifier)
        .setFollowing(row.subAccountId, true);
    ref
        .read(discoveryStateProvider.notifier)
        .setFollowState(row.subAccountId, true);
    ref
        .read(clientStateSyncOutboxProvider.notifier)
        .enqueueFollow(
          subAccountId: row.subAccountId,
          currentFollowing: currentFollowing,
          shouldFollow: true,
        );
  }

  Future<void> _showFollowingActionSheet(
    ProfileSocialRelationRowViewData row,
  ) async {
    final capability = _resolvedCapability(row);
    final canMessage =
        capability.canSendMessage ||
        capability.canOpenConversation ||
        capability.hasFormalConversation ||
        capability.canCreateDirectConversation;
    final result = await showAppActionSheet<String>(
      context,
      title: row.displayName,
      message: '@${row.userHandle}',
      sections: <AppActionSheetSection<String>>[
        AppActionSheetSection<String>(
          items: <AppActionSheetItem<String>>[
            AppActionSheetItem<String>(
              label: UITextConstants.profileStatsUnfollow,
              value: 'unfollow',
              isDestructive: true,
            ),
            AppActionSheetItem<String>(
              label: UITextConstants.profileDirectMessage,
              value: 'message',
              description: canMessage
                  ? null
                  : UITextConstants.profileStatsMessageUnavailable,
              enabled: canMessage,
            ),
          ],
        ),
      ],
    );
    if (!mounted || result == null) {
      return;
    }
    if (result == 'unfollow') {
      _trackAction(
        'unfollow_confirm',
        targetType: 'profile',
        targetKey: row.subAccountId,
        payload: <String, dynamic>{
          'tab': _activeTab.routeValue,
          'surfaceId': 'profile_stats',
        },
      );
      ref
          .read(userRelationshipStateProvider.notifier)
          .setFollowing(row.subAccountId, false);
      ref
          .read(discoveryStateProvider.notifier)
          .setFollowState(row.subAccountId, false);
      ref
          .read(clientStateSyncOutboxProvider.notifier)
          .enqueueFollow(
            subAccountId: row.subAccountId,
            currentFollowing: true,
            shouldFollow: false,
          );
      if ((_bundle?.viewerContext.isOwner ?? false) &&
          _activeTab == _ProfileStatsTab.following) {
        setState(() {
          _activeMemory.items = _activeMemory.items
              .where(
                (item) =>
                    (item as ProfileSocialRelationRowViewData).subAccountId !=
                    row.subAccountId,
              )
              .toList(growable: false);
        });
      }
      return;
    }
    await _openDirectConversation(row);
  }

  Future<void> _openDirectConversation(
    ProfileSocialRelationRowViewData row,
  ) async {
    if (!await requireLogin(ref, context, AuthGateReason.sendMessage)) {
      return;
    }
    try {
      final created = await ref
          .read(chatRepositoryProvider)
          .createConversation(
            type: 'direct',
            initialMemberIds: <String>[row.subAccountId],
          );
      if (!mounted || created.conversationId.trim().isEmpty) {
        return;
      }
      _trackAction(
        'message_open',
        targetType: 'profile',
        targetKey: row.subAccountId,
        payload: <String, dynamic>{
          'tab': _activeTab.routeValue,
          'surfaceId': 'profile_stats',
        },
      );
      context.push(AppRoutePaths.chatDetail(id: created.conversationId));
    } catch (error) {
      if (!mounted) {
        return;
      }
      final semantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.global,
      );
      await AppActionErrorFeedback.show(context, semantic: semantic);
    }
  }

  void _openUserProfile(ProfileSocialRelationRowViewData row) {
    _trackAction(
      'row_click',
      targetType: 'profile',
      targetKey: row.subAccountId,
      payload: <String, dynamic>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
      },
    );
    context.push(
      AppRoutePaths.userProfile(username: row.subAccountId),
      extra: UserProfileRouteExtra(
        subAccountId: row.subAccountId,
        avatar: row.avatarUrl.isNotEmpty ? row.avatarUrl : null,
        displayName: row.displayName.isNotEmpty ? row.displayName : null,
      ),
    );
  }

  void _openCircle(CircleDto circle) {
    _trackAction(
      'row_click',
      targetType: 'circle',
      targetKey: circle.id,
      entityType: 'circle',
      entityId: circle.id,
      payload: <String, dynamic>{
        'tab': _activeTab.routeValue,
        'surfaceId': 'profile_stats',
      },
    );
    context.push(AppRoutePaths.circleDetail(id: circle.id));
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final body = _buildBody(context, isDark);
    return SettingsInsetMemberPickerPageScaffold(
      isDark: isDark,
      title: '',
      middle: _buildSegmentedControl(context),
      onBack: () => context.pop(),
      body: body,
    );
  }
}
