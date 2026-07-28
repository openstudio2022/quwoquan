import 'dart:async';
import 'package:quwoquan_app/core/widgets/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lpinyin/lpinyin.dart';

import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/services/user/contact_discovery_repository.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/core/widgets/app_search_field.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/core/widgets/error_states/app_error_states.dart';
import 'package:quwoquan_app/ui/user/models/contact_candidate_vm.dart';
import 'package:quwoquan_app/ui/user/services/contact_hash_service.dart';
import 'package:quwoquan_app/ui/user/widgets/contact_candidate_row.dart';

enum _PhoneContactsStatus {
  initial,
  loading,
  denied,
  ready,
  unavailable,
  error,
}

/// 手机通讯录页：权限三态 + 本机哈希匹配 + 能力位驱动添加。
///
/// 手机号仅在本机经 [ContactHashService] 规范化哈希后用于匹配，原文不上传、不出库。
class PhoneContactsPage extends ConsumerStatefulWidget {
  const PhoneContactsPage({super.key});

  @override
  ConsumerState<PhoneContactsPage> createState() => _PhoneContactsPageState();
}

class _PhoneContactsPageState extends ConsumerState<PhoneContactsPage> {
  static const ContactHashService _hasher = ContactHashService();

  _PhoneContactsStatus _status = _PhoneContactsStatus.initial;
  bool _permanentlyDenied = false;
  String _query = '';
  List<ContactCandidateVm> _matches = <ContactCandidateVm>[];
  final Set<String> _pending = <String>{};
  Object? _rawError;

  @override
  void initState() {
    super.initState();
    final caps = ref.read(platformCapabilitiesProvider);
    if (!caps.contacts) {
      _status = _PhoneContactsStatus.unavailable;
    }
  }

  Future<void> _requestAndLoad() async {
    setState(() {
      _rawError = null;
      _status = _PhoneContactsStatus.loading;
    });
    AppPermissionEnsureOutcome outcome;
    try {
      outcome = await AppPermissionCoordinator.current.ensure(
        context,
        AppPermissionKind.contacts,
        surface: AppPermissionSurface.page,
        showUiOnFailure: false,
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _rawError = error;
          _status = _PhoneContactsStatus.error;
        });
      }
      return;
    }
    if (!mounted) {
      return;
    }
    if (outcome != AppPermissionEnsureOutcome.granted) {
      setState(() {
        _permanentlyDenied =
            outcome == AppPermissionEnsureOutcome.settingsRequired ||
            outcome == AppPermissionEnsureOutcome.restricted;
        _status = _PhoneContactsStatus.denied;
      });
      return;
    }
    await _load();
  }

  Future<void> _openContactsSettings() async {
    setState(() => _status = _PhoneContactsStatus.loading);
    final opened = await AppPermissionCoordinator.current.openSettings(
      AppPermissionKind.contacts,
      onReturn: (granted) {
        if (!mounted) {
          return;
        }
        if (granted) {
          unawaited(_load());
          return;
        }
        setState(() => _status = _PhoneContactsStatus.denied);
      },
    );
    if (!opened && mounted) {
      setState(() => _status = _PhoneContactsStatus.denied);
    }
  }

  Future<void> _load() async {
    try {
      final contacts = await FlutterContacts.getAll(
        properties: const <ContactProperty>{ContactProperty.phone},
      );
      // 本机姓名按 hash 建索引，匹配命中后回显通讯录里的称呼。
      final nameByHash = <String, String>{};
      final phones = <String>[];
      for (final contact in contacts) {
        for (final phone in contact.phones) {
          final hashed = _hasher.hash(phone.number);
          if (hashed.isEmpty) {
            continue;
          }
          phones.add(phone.number);
          nameByHash.putIfAbsent(hashed, () => contact.displayName ?? '');
        }
      }
      final hashed = _hasher.hashAll(phones);
      if (hashed.isEmpty) {
        if (mounted) {
          setState(() {
            _matches = <ContactCandidateVm>[];
            _status = _PhoneContactsStatus.ready;
          });
        }
        return;
      }
      final result = await ref
          .read(contactDiscoveryRepositoryProvider)
          .initiate(hashed);
      if (!mounted) {
        return;
      }
      setState(() {
        _matches = result.matches
            .map((m) => _toCandidate(m, nameByHash[m.hashedPhone]))
            .toList(growable: false);
        _status = _PhoneContactsStatus.ready;
      });
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'contact_discovery',
              action: 'match_phone_contacts',
              pageName: 'PhoneContactsPage',
              targetType: 'contact_discovery',
              targetKey: result.id,
              payload: <String, Object?>{
                'result': 'success',
                'resultCount': result.matchCount,
              },
            ),
      );
    } catch (error) {
      if (mounted) {
        setState(() {
          _rawError = error;
          _status = _PhoneContactsStatus.error;
        });
      }
    }
  }

  ContactCandidateVm _toCandidate(
    ContactDiscoveryMatchView match,
    String? localName,
  ) {
    final capability = match.relationshipCapability;
    return ContactCandidateVm(
      subAccountId: match.subAccountId,
      displayName: localName?.trim().isNotEmpty == true
          ? localName!.trim()
          : match.displayName,
      userHandle: match.userHandle,
      avatarUrl: match.avatarUrl,
      avatarVersion: match.avatarVersion,
      region: match.region,
      subtitle: match.displayName,
      addState: ContactCandidateVm.addStateFromCapability(
        relationState: capability.relationState,
        canFollow: capability.canFollow,
        canUnfollow: capability.canUnfollow,
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
          .read(userRelationshipStateProvider.notifier)
          .setFollowingWithSync(
            candidate.subAccountId,
            currentFollowing: false,
            shouldFollow: true,
            sourceSurface: AppUiSurfaces.addContactPhone,
          );
      if (!mounted) {
        return;
      }
      setState(() {
        _matches = _matches
            .map(
              (c) => c.subAccountId == candidate.subAccountId
                  ? c.copyWith(addState: ContactAddState.added)
                  : c,
            )
            .toList(growable: false);
      });
      AppToast.show(context, ContactText.addContactConfirmedToast);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'follow_contact_from_phone',
              pageName: 'PhoneContactsPage',
              targetType: 'user',
              targetKey: candidate.subAccountId,
            ),
      );
    } catch (error) {
      if (mounted) {
        await AppActionErrorFeedback.show(
          context,
          semantic: runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.submit,
            scope: UiErrorScope.dialog,
          ),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _add(candidate);
            }
          },
        );
      }
    } finally {
      if (mounted) {
        setState(() => _pending.remove(candidate.subAccountId));
      }
    }
  }

  List<ContactCandidateVm> get _filtered {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) {
      return _matches;
    }
    return _matches
        .where(
          (c) =>
              c.displayName.toLowerCase().contains(q) ||
              c.userHandle.toLowerCase().contains(q) ||
              (c.subtitle ?? '').toLowerCase().contains(q),
        )
        .toList(growable: false);
  }

  /// 按 lpinyin 首字母分组（A–Z, #），返回有序 keys + map。
  ({List<String> keys, Map<String, List<ContactCandidateVm>> map}) _group(
    List<ContactCandidateVm> list,
  ) {
    final map = <String, List<ContactCandidateVm>>{};
    for (final c in list) {
      final name = c.displayName.trim();
      var letter = '#';
      if (name.isNotEmpty) {
        final shorts = PinyinHelper.getShortPinyin(name);
        final source = shorts.isNotEmpty ? shorts : name;
        final first = source.substring(0, 1).toUpperCase();
        if (RegExp(r'[A-Z]').hasMatch(first)) {
          letter = first;
        }
      }
      map.putIfAbsent(letter, () => <ContactCandidateVm>[]).add(c);
    }
    final keys = map.keys.toList()..sort();
    if (keys.remove('#')) {
      keys.add('#');
    }
    return (keys: keys, map: map);
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
          ContactText.addContactPhoneEntryTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
      ),
      body: SafeArea(child: _buildBody(context)),
    );
  }

  Widget _buildBody(BuildContext context) {
    switch (_status) {
      case _PhoneContactsStatus.unavailable:
        return _CenteredHint(text: ContactText.phoneContactsUnavailable);
      case _PhoneContactsStatus.initial:
        return _PermissionGate(
          title: ContactText.phoneContactsPermissionTitle,
          body: ContactText.phoneContactsPermissionBody,
          cta: ContactText.phoneContactsPermissionCta,
          onPressed: () => unawaited(_requestAndLoad()),
        );
      case _PhoneContactsStatus.loading:
        return AppRequestFeedback.section();
      case _PhoneContactsStatus.denied:
        return _PermissionGate(
          title: ContactText.phoneContactsPermissionDenied,
          body: ContactText.phoneContactsPermissionBody,
          cta: _permanentlyDenied
              ? FoundationText.openSettings
              : ContactText.phoneContactsPermissionCta,
          onPressed: _permanentlyDenied
              ? () => unawaited(_openContactsSettings())
              : () => unawaited(_requestAndLoad()),
        );
      case _PhoneContactsStatus.ready:
        return _buildReady(context);
      case _PhoneContactsStatus.error:
        return AppPageErrorState(
          semantic: runtimeErrorSemantic(
            context,
            error: _rawError!,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          ),
          onAction: (action) async {
            if (action.type == UiErrorActionType.retry) {
              await _requestAndLoad();
            }
          },
        );
    }
  }

  Widget _buildReady(BuildContext context) {
    final filtered = _filtered;
    return Column(
      children: <Widget>[
        Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: AppSearchField(
            placeholder: ContactText.phoneContactsSearchPlaceholder,
            onChanged: (value) => setState(() => _query = value),
          ),
        ),
        if (_matches.isNotEmpty) ...<Widget>[
          Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    UITextConstants.phoneContactsMatchedCount(_matches.length),
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
        ],
        Expanded(child: _buildList(context, filtered)),
      ],
    );
  }

  Widget _buildList(BuildContext context, List<ContactCandidateVm> list) {
    if (list.isEmpty) {
      return _CenteredHint(
        text: _matches.isEmpty
            ? ContactText.phoneContactsNoMatch
            : ContactText.addContactSearchNoResult,
      );
    }
    final grouped = _group(list);
    final children = <Widget>[];
    for (final key in grouped.keys) {
      children.add(_SectionHeader(letter: key));
      for (final candidate in grouped.map[key]!) {
        children.add(
          ContactCandidateRow(
            candidate: candidate,
            pending: _pending.contains(candidate.subAccountId),
            onAdd: () => unawaited(_add(candidate)),
            onTap: () => context.push(
              AppRoutePaths.addContactConfirm(
                handle: candidate.userHandle,
                userId: candidate.subAccountId,
                source: 'phone',
              ),
            ),
          ),
        );
      }
    }
    children.add(
      Padding(
        padding: EdgeInsets.all(AppSpacing.containerLg),
        child: Text(
          ContactText.addContactPrivacyHashNote,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            color: AppColors.iosTertiaryLabel(context),
          ),
        ),
      ),
    );
    return ListView(children: children);
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.letter});

  final String letter;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      color: AppColors.iosPageBackground(context),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.intraGroupSm,
      ),
      child: Text(
        letter,
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          fontWeight: AppTypography.semiBold,
          color: AppColors.iosSecondaryLabel(context),
        ),
      ),
    );
  }
}

class _PermissionGate extends StatelessWidget {
  const _PermissionGate({
    required this.title,
    required this.body,
    required this.cta,
    required this.onPressed,
  });

  final String title;
  final String body;
  final String cta;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerXl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(
              CupertinoIcons.person_2_fill,
              size: AppSpacing.iconLarge,
              color: AppColors.iosAccent(context),
            ),
            SizedBox(height: AppSpacing.containerMd),
            Text(
              title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosTitle3,
                fontWeight: AppTypography.semiBold,
                color: AppColors.iosLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              body,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.base,
                color: AppColors.iosSecondaryLabel(context),
              ),
            ),
            SizedBox(height: AppSpacing.containerLg),
            CupertinoButton(
              borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
              color: AppColors.iosAccent(context),
              onPressed: onPressed,
              child: Text(
                cta,
                style: TextStyle(
                  fontSize: AppTypography.iosBody,
                  fontWeight: AppTypography.semiBold,
                  color: AppColors.white,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CenteredHint extends StatelessWidget {
  const _CenteredHint({required this.text});

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
