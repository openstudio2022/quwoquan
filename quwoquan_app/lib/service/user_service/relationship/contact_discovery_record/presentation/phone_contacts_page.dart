import 'dart:async';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:lpinyin/lpinyin.dart';

import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/application/public/contact_discovery_repository.dart';
import 'package:quwoquan_app/design_system/semantics/navigation_semantic_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/runtime/platform/permissions/app_permission_coordinator.dart';
import 'package:quwoquan_app/runtime/platform/platform_providers.dart'
    show deviceContactsGatewayProvider;
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/search/app_search_field.dart';
import 'package:quwoquan_app/design_system/feedback/app_toast.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/contact_candidate_vm.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/relationship/contact_discovery_record/adapters/contact_hash_service.dart';
import 'package:quwoquan_app/runtime/di/user_presentation_slots.dart';

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
  static const Duration _deviceContactsReadTimeout = Duration(seconds: 8);
  static const Duration _followReadbackTimeout = Duration(seconds: 10);

  _PhoneContactsStatus _status = _PhoneContactsStatus.initial;
  bool _permanentlyDenied = false;
  String _query = '';
  List<ContactCandidateVm> _matches = <ContactCandidateVm>[];
  final Set<String> _pending = <String>{};
  final Map<String, int> _followAttemptByTarget = <String, int>{};
  Object? _rawError;
  int _loadGeneration = 0;
  int _followAttemptSequence = 0;

  @override
  void initState() {
    super.initState();
    final caps = ref.read(platformCapabilitiesProvider);
    if (!caps.contacts) {
      _status = _PhoneContactsStatus.unavailable;
    }
  }

  Future<void> _requestAndLoad() async {
    final generation = _beginLoad();
    AppPermissionEnsureOutcome outcome;
    try {
      outcome = await AppPermissionCoordinator.current.ensure(
        context,
        AppPermissionKind.contacts,
        surface: AppPermissionSurface.page,
        showUiOnFailure: false,
      );
    } catch (error) {
      if (_isCurrentLoad(generation)) {
        setState(() {
          _rawError = error;
          _status = _PhoneContactsStatus.error;
        });
      }
      return;
    }
    if (!_isCurrentLoad(generation)) {
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
    await _load(generation);
  }

  Future<void> _openContactsSettings() async {
    final generation = _beginLoad();
    final opened = await AppPermissionCoordinator.current.openSettings(
      AppPermissionKind.contacts,
      onReturn: (granted) {
        if (!_isCurrentLoad(generation)) {
          return;
        }
        if (granted) {
          unawaited(_load(generation));
          return;
        }
        setState(() => _status = _PhoneContactsStatus.denied);
      },
    );
    if (!opened && _isCurrentLoad(generation)) {
      setState(() => _status = _PhoneContactsStatus.denied);
    }
  }

  Future<void> _load(int generation) async {
    try {
      final contacts = await ref
          .read(deviceContactsGatewayProvider)
          .readContacts(timeout: _deviceContactsReadTimeout);
      if (!_isCurrentLoad(generation)) {
        return;
      }
      // 本机姓名按 hash 建索引，匹配命中后回显通讯录里的称呼。
      final nameByHash = <String, String>{};
      final phones = <String>[];
      for (final contact in contacts) {
        for (final phone in contact.phoneNumbers) {
          final hashedPhone = _hasher.hash(phone);
          if (hashedPhone.isEmpty) {
            continue;
          }
          phones.add(phone);
          nameByHash.putIfAbsent(hashedPhone, () => contact.displayName);
        }
      }
      final hashedPhones = _hasher.hashAll(phones);
      if (hashedPhones.isEmpty) {
        if (_isCurrentLoad(generation)) {
          setState(() {
            _matches = <ContactCandidateVm>[];
            _status = _PhoneContactsStatus.ready;
          });
        }
        return;
      }
      final result = await ref
          .read(contactDiscoveryRepositoryProvider)
          .initiate(hashedPhones);
      if (!_isCurrentLoad(generation)) {
        return;
      }
      setState(() {
        _matches = result.matches
            .map((match) => _toCandidate(match, nameByHash[match.hashedPhone]))
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
      if (_isCurrentLoad(generation)) {
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
      personaId: match.personaId,
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
        isBlocked: capability.isBlocked,
        isBlockedBy: capability.isBlockedBy,
      ),
    );
  }

  Future<void> _add(ContactCandidateVm candidate) async {
    final targetPersonaId = candidate.personaId.trim();
    final currentCandidate = _candidate(targetPersonaId);
    if (targetPersonaId.isEmpty ||
        currentCandidate == null ||
        !currentCandidate.addState.canTriggerAdd ||
        _pending.contains(targetPersonaId)) {
      return;
    }
    final resultGeneration = _loadGeneration;
    final attempt = ++_followAttemptSequence;
    Object? failure;
    setState(() {
      _pending.add(targetPersonaId);
      _followAttemptByTarget[targetPersonaId] = attempt;
    });
    try {
      final capabilityRepository = ref.read(
        relationshipCapabilityRepositoryForSurfaceProvider(
          AppUiSurfaces.addContactPhone,
        ),
      );
      final preflight = await capabilityRepository
          .getCapability(targetPersonaId)
          .timeout(_followReadbackTimeout);
      _requireFollowPreflight(preflight, targetPersonaId);
      if (!_isCurrentFollowAttempt(
        targetPersonaId,
        attempt,
        resultGeneration,
      )) {
        return;
      }
      await ref
          .read(
            personaRelationshipCommandWriterProvider(
              AppUiSurfaces.addContactPhone,
            ),
          )
          .follow(
            targetPersonaId,
            sourceSurfaceId: AppUiSurfaces.addContactPhone.id,
          );
      if (!_isCurrentFollowAttempt(
        targetPersonaId,
        attempt,
        resultGeneration,
      )) {
        return;
      }
      final confirmed = await capabilityRepository
          .getCapability(targetPersonaId)
          .timeout(_followReadbackTimeout);
      _requireFollowReadback(confirmed, targetPersonaId);
      if (!_isCurrentFollowAttempt(
        targetPersonaId,
        attempt,
        resultGeneration,
      )) {
        return;
      }
      setState(() {
        _matches = _matches
            .map(
              (c) => c.personaId == targetPersonaId
                  ? c.copyWith(addState: ContactAddState.added)
                  : c,
            )
            .toList(growable: false);
      });
      if (!mounted) {
        return;
      }
      AppToast.show(context, ContactText.addContactConfirmedToast);
      unawaited(
        ref
            .read(journeyEventTrackerProvider)
            .trackAction(
              journey: 'relationship',
              action: 'follow_contact_from_phone',
              pageName: 'PhoneContactsPage',
              targetType: 'user',
              targetKey: targetPersonaId,
            ),
      );
    } catch (error) {
      if (_isCurrentFollowAttempt(targetPersonaId, attempt, resultGeneration)) {
        failure = error;
      }
    } finally {
      if (_isCurrentFollowAttempt(targetPersonaId, attempt, resultGeneration)) {
        setState(() => _pending.remove(targetPersonaId));
      }
    }
    if (failure == null ||
        !_isCurrentFollowAttempt(targetPersonaId, attempt, resultGeneration)) {
      return;
    }
    if (!mounted) {
      return;
    }
    await AppActionErrorFeedback.show(
      context,
      semantic: ensureRetryUiErrorSemantic(
        runtimeErrorSemantic(
          context,
          error: failure,
          category: UiErrorCategory.submit,
          scope: UiErrorScope.dialog,
        ),
      ),
      onAction: (action) async {
        if (action.type != UiErrorActionType.retry &&
            action.type != UiErrorActionType.resubmit) {
          return;
        }
        final retryCandidate = _candidate(targetPersonaId);
        if (retryCandidate != null) {
          await _add(retryCandidate);
        }
      },
    );
  }

  int _beginLoad() {
    final generation = ++_loadGeneration;
    _followAttemptByTarget.clear();
    setState(() {
      _pending.clear();
      _rawError = null;
      _status = _PhoneContactsStatus.loading;
    });
    return generation;
  }

  bool _isCurrentLoad(int generation) =>
      mounted && _loadGeneration == generation;

  bool _isCurrentFollowAttempt(
    String targetPersonaId,
    int attempt,
    int resultGeneration,
  ) =>
      mounted &&
      _loadGeneration == resultGeneration &&
      _followAttemptByTarget[targetPersonaId] == attempt;

  ContactCandidateVm? _candidate(String targetPersonaId) {
    for (final candidate in _matches) {
      if (candidate.personaId == targetPersonaId) {
        return candidate;
      }
    }
    return null;
  }

  void _requireFollowPreflight(
    RelationshipCapabilityViewData capability,
    String targetPersonaId,
  ) {
    if (capability.targetPersonaId.trim() != targetPersonaId ||
        !capability.canFollow ||
        capability.viewerFollowsTarget ||
        capability.isSelf ||
        capability.isBlocked ||
        capability.isBlockedBy) {
      throw StateError('FollowUser is not allowed by current capability');
    }
  }

  void _requireFollowReadback(
    RelationshipCapabilityViewData capability,
    String targetPersonaId,
  ) {
    if (capability.targetPersonaId.trim() != targetPersonaId ||
        !capability.viewerFollowsTarget ||
        capability.isBlocked ||
        capability.isBlockedBy) {
      throw StateError(
        'FollowUser did not converge in authoritative relationship state',
      );
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
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry) {
              await _requestAndLoad();
              return _status == _PhoneContactsStatus.ready
                  ? UiRecoveryOutcome.recovered
                  : UiRecoveryOutcome.stillBlocked;
            }
            return UiRecoveryOutcome.cancelled;
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
          ref.watch(contactCandidateRowBuilderProvider)(
            candidate: candidate,
            pending: _pending.contains(candidate.personaId),
            onAdd: () => unawaited(_add(candidate)),
            onTap: () => context.push(
              AppRoutePaths.addContactConfirm(
                handle: candidate.userHandle,
                userId: candidate.personaId,
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
