import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/models/search_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/user/models/contact_candidate_vm.dart';
import 'package:quwoquan_app/ui/user/widgets/contact_candidate_row.dart';

/// 添加联系人搜索结果页：趣我圈号(精确)/昵称(模糊) 查找 + 能力位驱动添加。
class ContactSearchResultPage extends ConsumerStatefulWidget {
  const ContactSearchResultPage({super.key, this.initialQuery = ''});

  final String initialQuery;

  @override
  ConsumerState<ContactSearchResultPage> createState() =>
      _ContactSearchResultPageState();
}

class _ContactSearchResultPageState
    extends ConsumerState<ContactSearchResultPage> {
  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  String _query = '';
  bool _loading = false;
  List<ContactCandidateVm> _results = <ContactCandidateVm>[];
  final Set<String> _pending = <String>{};

  @override
  void initState() {
    super.initState();
    if (widget.initialQuery.isNotEmpty) {
      _controller.text = widget.initialQuery;
      _query = widget.initialQuery;
      unawaited(_runSearch(widget.initialQuery));
    }
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onChanged(String value) {
    setState(() => _query = value);
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 320), () {
      unawaited(_runSearch(value));
    });
  }

  Future<void> _runSearch(String value) async {
    final query = value.trim();
    if (query.isEmpty) {
      setState(() {
        _results = <ContactCandidateVm>[];
        _loading = false;
      });
      return;
    }
    setState(() => _loading = true);
    try {
      final items = await ref
          .read(userProfileRepositoryProvider)
          .searchSocialRelations(query: query);
      if (!mounted || _query.trim() != query) {
        return;
      }
      setState(() {
        _results = items.map(_toCandidate).toList(growable: false);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _results = <ContactCandidateVm>[];
        _loading = false;
      });
    }
  }

  ContactCandidateVm _toCandidate(SocialRelationSearchItemView item) {
    final cap = item.relationshipCapability;
    return ContactCandidateVm(
      subAccountId: item.subAccountId,
      displayName: item.displayName,
      userHandle: item.username,
      avatarUrl: item.avatarUrl,
      avatarVersion: item.avatarVersion,
      subtitle: item.headline,
      addState: ContactCandidateVm.addStateFromCapability(
        relationState: cap.relationState,
        canFollow: cap.canFollow,
        canUnfollow: cap.canUnfollow,
      ),
    );
  }

  Future<void> _add(ContactCandidateVm candidate) async {
    if (_pending.contains(candidate.subAccountId)) {
      return;
    }
    setState(() => _pending.add(candidate.subAccountId));
    try {
      await ref
          .read(userProfileRepositoryProvider)
          .followUser(candidate.subAccountId);
      if (!mounted) {
        return;
      }
      setState(() {
        _results = _results
            .map(
              (c) => c.subAccountId == candidate.subAccountId
                  ? c.copyWith(addState: ContactAddState.added)
                  : c,
            )
            .toList(growable: false);
      });
      AppToast.show(context, UITextConstants.addContactConfirmedToast);
    } catch (_) {
      if (mounted) {
        AppToast.show(context, UITextConstants.addContactFailedMessage);
      }
    } finally {
      if (mounted) {
        setState(() => _pending.remove(candidate.subAccountId));
      }
    }
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
              context.go(AppRoutePaths.addContact);
            }
          },
        ),
        middle: Text(
          UITextConstants.addContactSearchTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: <Widget>[
            Padding(
              padding: EdgeInsets.all(AppSpacing.containerMd),
              child: AppSearchField(
                controller: _controller,
                autofocus: widget.initialQuery.isEmpty,
                placeholder: UITextConstants.addContactSearchHubPlaceholder,
                onChanged: _onChanged,
                onSubmitted: (value) => unawaited(_runSearch(value)),
              ),
            ),
            Expanded(child: _buildResults(context)),
          ],
        ),
      ),
    );
  }

  Widget _buildResults(BuildContext context) {
    if (_loading && _results.isEmpty) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_query.trim().isEmpty) {
      return _Hint(text: UITextConstants.addContactSearchEmptyPrompt);
    }
    if (_results.isEmpty) {
      return _Hint(text: UITextConstants.addContactSearchNoResult);
    }
    return ListView.builder(
      itemCount: _results.length,
      itemBuilder: (context, index) {
        final candidate = _results[index];
        return ContactCandidateRow(
          candidate: candidate,
          pending: _pending.contains(candidate.subAccountId),
          onAdd: () => unawaited(_add(candidate)),
          onTap: () => context.push(
            AppRoutePaths.addContactConfirm(
              handle: candidate.userHandle,
              userId: candidate.subAccountId,
              source: 'search',
            ),
          ),
        );
      },
    );
  }
}

class _Hint extends StatelessWidget {
  const _Hint({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: Text(
          text,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.base,
            color: AppColors.iosSecondaryLabel(context),
          ),
        ),
      ),
    );
  }
}
