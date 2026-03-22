import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/components.dart';
import 'package:quwoquan_app/core/models/assistant_open_context.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/models/user_profile_route_extra.dart';
import 'package:quwoquan_app/core/models/visit_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/search/providers/search_coordinator.dart';
import 'package:speech_to_text/speech_to_text.dart' as stt;

class GlobalSearchPage extends ConsumerStatefulWidget {
  const GlobalSearchPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<GlobalSearchPage> createState() => _GlobalSearchPageState();
}

class _GlobalSearchPageState extends ConsumerState<GlobalSearchPage> {
  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  final stt.SpeechToText _speechToText = stt.SpeechToText();
  bool _speechReady = false;

  SearchCoordinator get _coordinator =>
      ref.read(searchCoordinatorProvider(widget.launchContext));

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.launchContext.prefilledQuery);
    _focusNode = FocusNode();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    _focusNode.dispose();
    _speechToText.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final coordinator = ref.watch(searchCoordinatorProvider(widget.launchContext));
    final state = coordinator.state;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor = SettingsSemanticConstants.pageBackground(isDark);
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final dividerColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final cardColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final facetItems = state.sections
        .where((section) => section.kind == SearchSectionKind.circleFacets)
        .expand((section) => section.items)
        .where((item) => item.kind == SearchResultItemKind.circleFacet)
        .map((item) => item.cast<CircleFacetBucketView>())
        .toList(growable: false);
    _syncControllerText(state.query);

    return AppFullscreenModalSurface(
      surfaceKey: TestKeys.fullscreenModalSurface,
      backgroundColor: backgroundColor,
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerXs,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: CupertinoSearchTextField(
                  key: const ValueKey<String>('global_search_field'),
                  controller: _controller,
                  focusNode: _focusNode,
                  autofocus: true,
                  placeholder: UITextConstants.globalSearchTitle,
                  onChanged: (value) => _coordinator.updateQuery(value),
                  onSubmitted:
                      (value) => _coordinator.updateQuery(
                        value,
                        immediate: true,
                        persistToHistory: true,
                      ),
                ),
              ),
              if (state.isLoading) ...[
                SizedBox(width: AppSpacing.intraGroupSm),
                const CupertinoActivityIndicator(radius: 8),
              ],
              CupertinoButton(
                padding: EdgeInsets.only(left: AppSpacing.sm),
                onPressed: _handleClose,
                child: const Text(UITextConstants.cancel),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.containerSm),
          _QuickActionRow(
            isDark: isDark,
            isVoiceRunning: state.isVoiceRunning,
            onAskAssistant: () => _openAssistantHandoff(state),
            onVoiceInput: () => _toggleVoiceInput(state),
          ),
          SizedBox(height: AppSpacing.containerSm),
          _ScopeRow(
            scope: state.scope,
            onScopeChanged: coordinator.updateScope,
          ),
          if (state.hasQuery && facetItems.isNotEmpty) ...[
            SizedBox(height: AppSpacing.containerSm),
            _FacetRow(
              facets: facetItems,
              selectedFacet: state.selectedFacet,
              onFacetSelected: coordinator.updateFacet,
            ),
          ],
          SizedBox(height: AppSpacing.containerSm),
          Expanded(
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: cardColor.withValues(alpha: 0.45),
                borderRadius: BorderRadius.circular(
                  AppSpacing.contentPreviewCornerRadius,
                ),
                border: Border.all(color: dividerColor),
              ),
              child: AnimatedSwitcher(
                duration: const Duration(milliseconds: 180),
                child: state.hasQuery
                    ? _buildResultsView(state, fgPrimary, fgSecondary, isDark)
                    : _buildLandingView(state, fgPrimary, fgSecondary, isDark),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLandingView(
    SearchSessionState state,
    Color fgPrimary,
    Color fgSecondary,
    bool isDark,
  ) {
    if (state.isHydratingHistory && state.recentSearches.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (state.recentSearches.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                CupertinoIcons.search_circle,
                size: AppSpacing.largeAvatarSize,
                color: fgSecondary,
              ),
              SizedBox(height: AppSpacing.containerSm),
              Text(
                '输入关键词，或试试问小趣和语音搜索',
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      );
    }
    return Column(
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.containerMd,
            AppSpacing.containerMd,
            AppSpacing.intraGroupSm,
          ),
          child: Row(
            children: [
              Text(
                '最近搜索',
                style: TextStyle(
                  fontSize: AppTypography.iosSubheadline,
                  fontWeight: AppTypography.semiBold,
                  color: fgPrimary,
                ),
              ),
              const Spacer(),
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _coordinator.clearRecentSearches,
                child: Text(
                  '清空',
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: AppColors.primaryColor,
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: ListView.separated(
            padding: EdgeInsets.fromLTRB(
              AppSpacing.containerMd,
              0,
              AppSpacing.containerMd,
              AppSpacing.containerMd,
            ),
            itemCount: state.recentSearches.length,
            separatorBuilder:
                (context, index) => SizedBox(height: AppSpacing.intraGroupXs),
            itemBuilder: (context, index) {
              final entry = state.recentSearches[index];
              return CupertinoListTile(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerSm,
                  vertical: AppSpacing.intraGroupXs,
                ),
                leading: Icon(
                  CupertinoIcons.time,
                  color: fgSecondary,
                  size: AppSpacing.iconMedium,
                ),
                title: Text(
                  entry.query,
                  style: TextStyle(
                    fontSize: AppTypography.iosBody,
                    color: fgPrimary,
                  ),
                ),
                subtitle: Text(
                  entry.scope.label,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: fgSecondary,
                  ),
                ),
                trailing: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => _coordinator.removeRecentSearch(entry.entryId),
                  child: Icon(
                    CupertinoIcons.xmark_circle_fill,
                    size: AppSpacing.iconMedium,
                    color: fgSecondary,
                  ),
                ),
                onTap: () {
                  _coordinator.useRecentSearch(entry);
                },
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildResultsView(
    SearchSessionState state,
    Color fgPrimary,
    Color fgSecondary,
    bool isDark,
  ) {
    final visibleSections = state.sections
        .where((section) => section.kind != SearchSectionKind.circleFacets)
        .toList(growable: false);
    final hasVisibleItems = visibleSections.any((section) => section.items.isNotEmpty);
    if (state.isLoading && !hasVisibleItems) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (!state.isLoading && !hasVisibleItems) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                CupertinoIcons.search,
                size: AppSpacing.largeAvatarSize,
                color: fgSecondary,
              ),
              SizedBox(height: AppSpacing.containerSm),
              Text(
                '没有找到相关结果',
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ),
      );
    }
    return ListView.builder(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
        AppSpacing.containerMd,
      ),
      itemCount: visibleSections.length,
      itemBuilder: (context, index) {
        final section = visibleSections[index];
        return Padding(
          padding: EdgeInsets.only(
            bottom: index == visibleSections.length - 1
                ? 0
                : AppSpacing.containerMd,
          ),
          child: _buildSection(
            section: section,
            isDark: isDark,
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
          ),
        );
      },
    );
  }

  Widget _buildSection({
    required SearchSection section,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              section.title,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.semiBold,
                color: fgPrimary,
              ),
            ),
            if (section.degraded) ...[
              SizedBox(width: AppSpacing.intraGroupSm),
              Text(
                '部分降级',
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: CupertinoColors.systemOrange.resolveFrom(context),
                ),
              ),
            ],
          ],
        ),
        SizedBox(height: AppSpacing.intraGroupSm),
        if (section.items.isEmpty && section.errorMessage != null)
          Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
            child: Text(
              section.errorMessage!,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: fgSecondary,
              ),
            ),
          )
        else
          Column(
            children: [
              for (var i = 0; i < section.items.length; i++) ...[
                _buildResultItem(
                  item: section.items[i],
                  isDark: isDark,
                  fgPrimary: fgPrimary,
                  fgSecondary: fgSecondary,
                ),
                if (i != section.items.length - 1)
                  SizedBox(height: AppSpacing.intraGroupSm),
              ],
            ],
          ),
      ],
    );
  }

  Widget _buildResultItem({
    required SearchResultItem item,
    required bool isDark,
    required Color fgPrimary,
    required Color fgSecondary,
  }) {
    switch (item.kind) {
      case SearchResultItemKind.post:
        final post = item.cast<PostSearchItemView>();
        return PostPreviewListTile(
          isDark: isDark,
          title: (post.title ?? post.summary ?? '内容').trim(),
          supportingText: post.summary ?? post.highlightText ?? '',
          coverUrl: post.coverUrl ?? '',
          eyebrowText: post.contentIdentity == 'moment' ? '动态' : '创作',
          showVideoBadge: post.contentType == 'video',
          footer: Text(
            post.authorDisplayName ?? '',
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openPostResult(post),
        );
      case SearchResultItemKind.socialRelation:
        final relation = item.cast<SocialRelationSearchItemView>();
        return _ResultRow(
          leading: _NetworkAvatar(
            imageUrl: relation.avatarUrl,
            fallbackIcon: CupertinoIcons.person_fill,
          ),
          title: relation.displayName,
          subtitle: relation.headline ?? relation.username,
          trailingLabel: relation.relationshipCapability.relationState,
          onTap: () => _openSocialRelation(relation),
        );
      case SearchResultItemKind.conversation:
        final conversation = item.cast<ConversationSearchItemView>();
        return _ResultRow(
          leading: _NetworkAvatar(
            imageUrl: conversation.avatarUrl,
            fallbackIcon: conversation.type == 'group'
                ? CupertinoIcons.person_2_fill
                : CupertinoIcons.chat_bubble_2_fill,
          ),
          title: conversation.title,
          subtitle:
              conversation.lastMessagePreview ??
              conversation.highlightText ??
              '打开聊天',
          trailingLabel: '会话',
          onTap: () => _openConversation(conversation.conversationId),
        );
      case SearchResultItemKind.message:
        final message = item.cast<MessageSearchItemView>();
        return _ResultRow(
          leading: _NetworkAvatar(
            imageUrl: message.senderAvatarUrl,
            fallbackIcon: CupertinoIcons.text_bubble_fill,
          ),
          title: message.senderDisplayName ?? message.conversationTitle ?? '消息',
          subtitle:
              '${message.conversationTitle ?? '聊天'} · ${message.contentPreview}',
          trailingLabel: '消息',
          onTap: () => _openConversation(message.conversationId),
        );
      case SearchResultItemKind.circle:
        final circle = item.cast<CircleSearchItemView>();
        return _ResultRow(
          leading: _NetworkAvatar(
            imageUrl: circle.coverUrl,
            fallbackIcon: CupertinoIcons.person_3_fill,
            roundedSquare: true,
          ),
          title: circle.name,
          subtitle: circle.description ?? circle.subCategory ?? '',
          trailingLabel: '圈子',
          onTap: () => _openCircle(circle.circleId),
        );
      case SearchResultItemKind.circleFacet:
        final facet = item.cast<CircleFacetBucketView>();
        return _ResultRow(
          leading: Icon(
            CupertinoIcons.square_grid_2x2_fill,
            size: AppSpacing.iconMedium,
            color: AppColors.primaryColor,
          ),
          title: facet.label,
          subtitle: '${facet.facetCount} 个圈子',
          trailingLabel: '频道',
          onTap: () => _coordinator.updateFacet(facet.subCategory ?? facet.facetKey),
        );
    }
  }

  Future<void> _openPostResult(PostSearchItemView item) async {
    unawaited(_coordinator.rememberCurrentQuery());
    try {
      final raw = await ref.read(contentRepositoryProvider).getPost(
        postId: item.postId,
      );
      if (!mounted) {
        return;
      }
      final dto = postBaseDtoFromMap(raw);
      if (dto.identity == 'work' && dto.displayFormat == 'note') {
        context.push(AppRoutePaths.articleDetail(id: dto.id));
        return;
      }
      final extra = MediaViewerExtra(
        posts: <PostSummaryView>[PostSummaryView.fromDto(dto)],
        dtoPosts: <PostBaseDto>[dto],
        initialIndex: 0,
        category: dto.identity == 'moment' ? 'moment' : dto.displayFormat,
        rawPostsById: <String, Map<String, dynamic>>{dto.id: raw},
      );
      if (dto.isVideoLike) {
        context.push(
          AppRoutePaths.videoViewer(index: '0'),
          extra: extra,
        );
        return;
      }
      context.push(
        AppRoutePaths.mediaViewer(category: 'photo', index: '0'),
        extra: extra,
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      AppToast.show(context, '内容详情暂时不可用');
    }
  }

  void _openSocialRelation(SocialRelationSearchItemView relation) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(
      AppRoutePaths.userProfile(
        username: relation.username.isNotEmpty
            ? relation.username
            : relation.profileSubjectId,
      ),
      extra: UserProfileRouteExtra(
        profileSubjectId: relation.profileSubjectId,
        avatar: relation.avatarUrl,
        displayName: relation.displayName,
      ),
    );
  }

  void _openConversation(String conversationId) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.chatDetail(id: conversationId));
  }

  void _openCircle(String circleId) {
    unawaited(_coordinator.rememberCurrentQuery());
    context.push(AppRoutePaths.circleDetail(id: circleId));
  }

  void _openAssistantHandoff(SearchSessionState state) {
    final trimmedQuery = state.query.trim();
    final surfaceId = trimmedQuery.isEmpty
        ? AppUiSurfaces.globalSearchLanding.id
        : AppUiSurfaces.globalSearchResults.id;
    context.push(
      AppRoutePaths.chatDetail(id: AppConceptConstants.assistantConversationId),
      extra: AssistantOpenContext(
        source: AssistantSource.search,
        visitTarget: const VisitTarget.page('global_search'),
        experienceLevel: ExperienceLevel.returning,
        hints: <String, dynamic>{
          if (trimmedQuery.isNotEmpty) 'autoSendQuery': trimmedQuery,
          if (trimmedQuery.isNotEmpty) 'sourceQuery': trimmedQuery,
          'sourceSurfaceId': surfaceId,
          'entrySurfaceId': state.launchContext.entrySurfaceId,
          'fromGlobalSearch': trimmedQuery.isNotEmpty,
        },
      ),
    );
  }

  Future<void> _toggleVoiceInput(SearchSessionState state) async {
    if (_speechToText.isListening) {
      await _speechToText.stop();
      _coordinator.setVoiceRunning(false);
      return;
    }
    final permission = await Permission.microphone.request();
    if (!permission.isGranted) {
      if (mounted) {
        AppToast.show(context, '未获得麦克风权限');
      }
      return;
    }
    if (!_speechReady) {
      _speechReady = await _speechToText.initialize(
        onStatus: (status) {
          if (status == 'done' || status == 'notListening') {
            _coordinator.setVoiceRunning(false);
          }
        },
        onError: (_) {
          _coordinator.setVoiceRunning(false);
          if (mounted) {
            AppToast.show(context, '语音识别暂时不可用');
          }
        },
      );
    }
    if (!_speechReady) {
      if (mounted) {
        AppToast.show(context, '语音识别暂时不可用');
      }
      return;
    }
    _coordinator.setVoiceRunning(true);
    await _speechToText.listen(
      onResult: (result) {
        final recognized = result.recognizedWords.trim();
        if (recognized.isEmpty) {
          return;
        }
        _controller.value = TextEditingValue(
          text: recognized,
          selection: TextSelection.collapsed(offset: recognized.length),
        );
        _coordinator.updateQuery(
          recognized,
          immediate: result.finalResult,
          persistToHistory: result.finalResult,
        );
      },
      localeId: 'zh_CN',
      listenOptions: stt.SpeechListenOptions(
        cancelOnError: true,
        partialResults: true,
        listenMode: stt.ListenMode.dictation,
      ),
    );
  }

  void _handleClose() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.home);
  }

  void _syncControllerText(String query) {
    if (_controller.text == query) {
      return;
    }
    _controller.value = TextEditingValue(
      text: query,
      selection: TextSelection.collapsed(offset: query.length),
    );
  }
}

class _QuickActionRow extends StatelessWidget {
  const _QuickActionRow({
    required this.isDark,
    required this.isVoiceRunning,
    required this.onAskAssistant,
    required this.onVoiceInput,
  });

  final bool isDark;
  final bool isVoiceRunning;
  final VoidCallback onAskAssistant;
  final VoidCallback onVoiceInput;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: _ActionCard(
            isDark: isDark,
            icon: CupertinoIcons.sparkles,
            title: '问小趣',
            subtitle: '直接切到私人助手',
            onTap: onAskAssistant,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupSm),
        Expanded(
          child: _ActionCard(
            isDark: isDark,
            icon: isVoiceRunning
                ? CupertinoIcons.stop_circle_fill
                : CupertinoIcons.mic_fill,
            title: isVoiceRunning ? '结束语音' : '语音输入',
            subtitle: 'ASR 转成搜索词',
            onTap: onVoiceInput,
            accentColor: isVoiceRunning
                ? CupertinoColors.systemRed.resolveFrom(context)
                : null,
          ),
        ),
      ],
    );
  }
}

class _ScopeRow extends StatelessWidget {
  const _ScopeRow({required this.scope, required this.onScopeChanged});

  final SearchScope scope;
  final ValueChanged<SearchScope> onScopeChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemBuilder: (context, index) {
          final value = SearchScope.values[index];
          final selected = value == scope;
          return _FilterChipButton(
            label: value.label,
            selected: selected,
            onTap: () => onScopeChanged(value),
          );
        },
        separatorBuilder:
            (context, index) => SizedBox(width: AppSpacing.intraGroupSm),
        itemCount: SearchScope.values.length,
      ),
    );
  }
}

class _FacetRow extends StatelessWidget {
  const _FacetRow({
    required this.facets,
    required this.selectedFacet,
    required this.onFacetSelected,
  });

  final List<CircleFacetBucketView> facets;
  final String? selectedFacet;
  final ValueChanged<String?> onFacetSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: AppSpacing.minInteractiveSize,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: facets.length + 1,
        separatorBuilder:
            (context, index) => SizedBox(width: AppSpacing.intraGroupSm),
        itemBuilder: (context, index) {
          if (index == 0) {
            return _FilterChipButton(
              label: '全部频道',
              selected: selectedFacet == null || selectedFacet!.isEmpty,
              onTap: () => onFacetSelected(null),
            );
          }
          final facet = facets[index - 1];
          final facetKey = facet.subCategory ?? facet.facetKey;
          return _FilterChipButton(
            label: '${facet.label} ${facet.facetCount}',
            selected: facetKey == selectedFacet,
            onTap: () => onFacetSelected(facetKey),
          );
        },
      ),
    );
  }
}

class _ActionCard extends StatelessWidget {
  const _ActionCard({
    required this.isDark,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
    this.accentColor,
  });

  final bool isDark;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  final Color? accentColor;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final iconColor = accentColor ?? AppColors.primaryColor;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated),
        borderRadius: BorderRadius.circular(AppSpacing.contentPreviewCornerRadius),
        border: Border.all(color: borderColor),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: [
            Icon(icon, size: AppSpacing.iconMedium, color: iconColor),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FilterChipButton extends StatelessWidget {
  const _FilterChipButton({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      minimumSize: Size(0, AppSpacing.minInteractiveSize),
      color: selected
          ? AppColors.primaryColor.withValues(alpha: isDark ? 0.26 : 0.14)
          : AppColorsFunctional.getColor(
              isDark,
              ColorType.surfaceElevated,
            ),
      borderRadius: BorderRadius.circular(AppSpacing.minInteractiveSize / 2),
      onPressed: onTap,
      child: Text(
        label,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          fontWeight: selected ? AppTypography.semiBold : AppTypography.regular,
          color: selected
              ? AppColors.primaryColor
              : AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
        ),
      ),
    );
  }
}

class _ResultRow extends StatelessWidget {
  const _ResultRow({
    required this.leading,
    required this.title,
    required this.subtitle,
    required this.trailingLabel,
    required this.onTap,
  });

  final Widget leading;
  final String title;
  final String subtitle;
  final String trailingLabel;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated),
        borderRadius: BorderRadius.circular(AppSpacing.contentPreviewCornerRadius),
        border: Border.all(color: borderColor),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: [
            leading,
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosBody,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    subtitle,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: fgSecondary,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Text(
              trailingLabel,
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: AppColors.primaryColor,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NetworkAvatar extends StatelessWidget {
  const _NetworkAvatar({
    required this.imageUrl,
    required this.fallbackIcon,
    this.roundedSquare = false,
  });

  final String? imageUrl;
  final IconData fallbackIcon;
  final bool roundedSquare;

  @override
  Widget build(BuildContext context) {
    final borderRadius = BorderRadius.circular(
      roundedSquare ? AppSpacing.contentPreviewCornerRadius : 999,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      CupertinoTheme.of(context).brightness == Brightness.dark,
      ColorType.foregroundSecondary,
    );
    final child = (imageUrl ?? '').trim().isNotEmpty
        ? Image.network(
            imageUrl!,
            fit: BoxFit.cover,
            errorBuilder:
                (context, error, stackTrace) =>
                    Icon(fallbackIcon, color: fgSecondary),
          )
        : Icon(fallbackIcon, color: fgSecondary);
    return ClipRRect(
      borderRadius: borderRadius,
      child: Container(
        width: AppSpacing.avatarUserMd,
        height: AppSpacing.avatarUserMd,
        color: fgSecondary.withValues(alpha: 0.12),
        alignment: Alignment.center,
        child: child,
      ),
    );
  }
}
