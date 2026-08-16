import 'package:quwoquan_app/service/content_service/content/post/application/public/author_impact_query.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_facets.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_edit_query.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/profile_query.dart';
import 'package:quwoquan_app/runtime/transport/models/cursor_page.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/profile_edit_models.dart';
import 'package:quwoquan_app/service/user_service/persona_management/persona/application/public/persona_profile_view_data.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/user_homepage_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/persona_relationship_view_data.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/relationship_capability_repository.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/application/public/social_relation_search_item_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import 'fixture_user_resolver.dart';
import 'user_profile_test_builder.dart';

String get kMockCurrentOwnerId => FixtureUserResolver.currentUserVariantUserId;

String get kMockCurrentPersonaId =>
    FixtureUserResolver.currentUserVariantPersonaId;

ProfileEditSnapshotData buildProfileEditSnapshotDataFromProfile({
  required PersonaProfileViewData profile,
  List<CredentialBindingView> credentials = const <CredentialBindingView>[],
}) {
  final phoneCredential = credentials
      .where((row) => row.credentialType == CredentialType.phone)
      .followedBy(
        credentials.where(
          (row) => row.credentialType == CredentialType.carrierPhone,
        ),
      )
      .cast<CredentialBindingView?>()
      .firstWhere((row) => row != null, orElse: () => null);
  final occupationTagRef = profile.identityTags
      .where((tag) => tag.startsWith('Audience/用户/职业/'))
      .cast<String?>()
      .firstWhere((tag) => tag != null, orElse: () => null);
  final interestTags = profile.identityTags
      .where((tag) => tag.startsWith('Audience/用户/兴趣偏好/'))
      .toList(growable: false);
  return ProfileEditSnapshotData(
    ownerUserId: profile.ownerUserId,
    personaId: profile.personaId,
    avatarUrl: profile.avatarUrl,
    avatarAssetId: '',
    avatarVersion: profile.avatarVersion,
    backgroundUrl: profile.backgroundUrl,
    backgroundAssetId: '',
    nickname: profile.displayName,
    gender: 'unspecified',
    birthDate: '',
    region: '',
    regionTagRef: '',
    userHandle: profile.userHandle.isEmpty
        ? profile.personaId
        : profile.userHandle,
    bio: profile.bio,
    occupationTagRef: occupationTagRef ?? '',
    interestTagRefs: interestTags,
    phoneCredential: phoneCredential == null
        ? null
        : ProfileCredentialSummaryData(
            credentialType: phoneCredential.credentialType.wireName,
            displayLabel: phoneCredential.displayLabel ?? '',
            isBound: phoneCredential.isActive,
          ),
  );
}

ProfileQrCardData buildProfileQrCardDataFromSnapshot(
  ProfileEditSnapshotData snapshot,
) {
  final handle = snapshot.userHandle.isEmpty
      ? snapshot.personaId
      : snapshot.userHandle;
  final encodedHandle = Uri.encodeComponent(handle);
  final url =
      'https://mock.quwoquan.local/u/$encodedHandle?qr=mock_$encodedHandle';
  return ProfileQrCardData(
    publicProfileUrl: 'https://mock.quwoquan.local/u/$encodedHandle',
    qrPayload: url,
    qrTokenId: 'qr_$handle',
    avatarUrl: snapshot.avatarUrl,
    displayName: snapshot.nickname,
    region: snapshot.region,
    shareText: url,
  );
}

/// 当前 Profile/AuthorImpact/PersonaRelationship Facet 的 local-contract
/// object double。生产 composition 与环境 App 不可达本文件。
///
/// 旧实现曾同时维护多套已退出 wire DTO、Persona 管理与凭据接口；本实现只保留
/// 类声明实际承诺的五个领域 Facet，并直接返回当前 ViewData/generated 类型。
class MockUserProfileRepository
    implements
        ProfileQuery,
        ProfileEditQuery,
        AuthorImpactQuery,
        PersonaRelationshipQuery,
        PersonaRelationshipCommandWriter {
  const MockUserProfileRepository();

  static final Set<String> _followingPersonaIds = <String>{};

  static Set<String> get _ownerLikePersonaIds => <String>{
    'me',
    'fixture_user_current',
    'user_001',
    kMockCurrentPersonaId,
    kMockCurrentOwnerId,
  };

  @override
  Future<PersonaProfileViewData> getUserProfile(String userId) async {
    final requested = userId.trim().isEmpty ? kMockCurrentPersonaId : userId;
    final resolved = FixtureUserResolver.resolvePersonaId(requested);
    final seed = FixtureUserResolver.profileWireFor(resolved);
    return _profileFromScenarioSeed(
      seed,
      fallbackPersonaId: resolved.isEmpty ? requested : resolved,
    );
  }

  @override
  Future<UserProfileStatsViewData> getUserStats(String userId) async {
    return UserProfileStatsViewData.fromProfile(await getUserProfile(userId));
  }

  @override
  Future<UserHomepageBundleViewData> getUserHomepageBundle(
    String personaId,
  ) async {
    final resolved = FixtureUserResolver.resolvePersonaId(personaId);
    final profile = await getUserProfile(resolved);
    final stats = UserProfileStatsViewData.fromProfile(profile);
    final isOwner =
        _ownerLikePersonaIds.contains(personaId) ||
        _ownerLikePersonaIds.contains(resolved);
    final capability = isOwner
        ? null
        : _relationshipCapability(
            targetPersonaId: profile.personaId,
            following: _followingPersonaIds.contains(profile.personaId),
          );
    return UserHomepageBundleViewData(
      profile: profile,
      stats: stats,
      relationshipCapability: capability,
      tabCounts: UserHomepageTabCountsViewData.fromStats(stats),
      viewerContext: UserHomepageViewerContextViewData(
        viewerPersonaId: isOwner ? profile.personaId : kMockCurrentPersonaId,
        isOwner: isOwner,
        isGuest: false,
        relationToTarget: isOwner
            ? 'self'
            : capability?.relationState ?? 'not_following',
        canViewFullProfile: true,
      ),
      cacheVersion: 'alpha-${profile.personaId}',
    );
  }

  @override
  Future<ProfileEditSnapshotData> getProfileEditSnapshot() async {
    final profile = await getUserProfile(kMockCurrentPersonaId);
    return buildProfileEditSnapshotDataFromProfile(profile: profile);
  }

  @override
  Future<ProfileQrCardData> getProfileQrCard() async {
    return buildProfileQrCardDataFromSnapshot(await getProfileEditSnapshot());
  }

  @override
  Future<ProfileQrResolveWire> resolveProfileQrToken({
    required String token,
    String handle = '',
  }) async {
    if (token.trim().isEmpty) {
      throw ArgumentError.value(token, 'token', 'must not be empty');
    }
    final personaId = handle.trim().isEmpty
        ? kMockCurrentPersonaId
        : FixtureUserResolver.resolvePersonaId(handle);
    return ProfileQrResolveWire(
      personaId: personaId,
      userHandle: personaId,
      publicProfileUrl: 'https://quwoquan.com/u/$personaId',
      scanStatus: 'accepted',
    );
  }

  @override
  Future<List<SocialRelationSearchItemViewData>> searchSocialRelations({
    required String query,
    int limit = SearchSocialRelationsQuery.defaultLimit,
  }) async {
    final normalized = query.trim().toLowerCase();
    final profiles = _scenarioProfiles()
        .map(_profileFromAccountScenarioSeed)
        .where(
          (profile) =>
              normalized.isEmpty ||
              profile.personaId.toLowerCase().contains(normalized) ||
              profile.userHandle.toLowerCase().contains(normalized) ||
              profile.displayName.toLowerCase().contains(normalized),
        )
        .map(
          (profile) => SocialRelationSearchItemViewData(
            personaId: profile.personaId,
            userHandle: profile.userHandle,
            displayName: profile.displayName,
            avatarUrl: profile.avatarUrl,
            headline: profile.bio,
            chatAvailable: true,
            relationshipCapability: _relationshipCapability(
              targetPersonaId: profile.personaId,
              following: _followingPersonaIds.contains(profile.personaId),
            ),
          ),
        )
        .toList(growable: false);
    final safeLimit = limit <= 0
        ? SearchSocialRelationsQuery.defaultLimit
        : limit;
    return profiles.length <= safeLimit
        ? profiles
        : profiles.sublist(0, safeLimit);
  }

  @override
  Future<AuthorImpactSummary> getAuthorImpact(String personaId) async {
    final resolved = _ownerLikePersonaIds.contains(personaId)
        ? 'fixture_user_current'
        : personaId;
    final entry = _authorImpactWireExample(resolved);
    if (entry == null) {
      return AuthorImpactSummary(
        authorId: personaId,
        total: 0,
        items: const <AuthorImpactItem>[],
      );
    }
    final map = _stringObjectMap(entry);
    final items = (map['items'] as List<Object?>? ?? const <Object?>[])
        .whereType<Map<Object?, Object?>>()
        .map(
          (item) => _authorImpactItemFromScenarioSeed(_stringObjectMap(item)),
        )
        .toList(growable: false);
    return AuthorImpactSummary(
      authorId: (map['authorId'] ?? personaId).toString(),
      total: _intValue(map['total']),
      items: items,
    );
  }

  @override
  Future<AuthorImpactEvidencePage> listAuthorImpactEvidence({
    required String personaId,
    required String impactId,
    String evidenceSnapshotId = '',
    String cursor = '',
    int limit = ListAuthorImpactEvidenceQuery.defaultLimit,
  }) async {
    final summary = await getAuthorImpact(personaId);
    final item = summary.items.where((candidate) {
      return candidate.impactId == impactId ||
          (evidenceSnapshotId.isNotEmpty &&
              candidate.evidenceSnapshotId == evidenceSnapshotId);
    }).firstOrNull;
    if (item == null) {
      return AuthorImpactEvidencePage(
        impactId: impactId,
        evidenceSnapshotId: evidenceSnapshotId,
        totalCount: 0,
        items: const <AuthorImpactEvidenceItem>[],
        nextCursor: '',
        hasMore: false,
      );
    }
    final rows = _evidenceRows(item);
    final start = int.tryParse(cursor) ?? 0;
    final safeStart = start.clamp(0, rows.length);
    final safeLimit = limit <= 0
        ? ListAuthorImpactEvidenceQuery.defaultLimit
        : limit.clamp(1, ListAuthorImpactEvidenceQuery.maximumLimit);
    final end = (safeStart + safeLimit).clamp(safeStart, rows.length);
    return AuthorImpactEvidencePage(
      impactId: item.impactId,
      evidenceSnapshotId: item.evidenceSnapshotId,
      totalCount: rows.length,
      items: rows.sublist(safeStart, end),
      nextCursor: end < rows.length ? '$end' : '',
      hasMore: end < rows.length,
    );
  }

  @override
  Future<void> follow(
    String targetPersonaId, {
    required String sourceSurfaceId,
  }) async {
    final normalized = targetPersonaId.trim();
    if (normalized.isEmpty) {
      throw ArgumentError.value(targetPersonaId, 'targetPersonaId');
    }
    _followingPersonaIds.add(normalized);
  }

  @override
  Future<void> unfollow(String targetPersonaId) async {
    _followingPersonaIds.remove(targetPersonaId.trim());
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowing({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  }) async {
    final rows = await Future.wait(_followingPersonaIds.map(_relationRow));
    return _page(rows, query: query, cursor: cursor, limit: limit);
  }

  @override
  Future<CursorPage<ProfileSocialRelationRowViewData>> listFollowers({
    required String personaId,
    String? query,
    String? cursor,
    int limit = PersonaRelationshipListQuery.defaultLimit,
  }) async {
    final row = await _relationRow(kMockCurrentPersonaId);
    return _page(
      <ProfileSocialRelationRowViewData>[row],
      query: query,
      cursor: cursor,
      limit: limit,
    );
  }

  Future<ProfileSocialRelationRowViewData> _relationRow(
    String personaId,
  ) async {
    final profile = await getUserProfile(personaId);
    return ProfileSocialRelationRowViewData(
      personaId: profile.personaId,
      userHandle: profile.userHandle,
      displayName: profile.displayName,
      avatarUrl: profile.avatarUrl,
      avatarVersion: profile.avatarVersion,
      profileVisibility: profile.profileVisibility,
      relationState: _followingPersonaIds.contains(profile.personaId)
          ? 'following'
          : 'followed_by',
      followedAt: DateTime.utc(2026, 7, 1),
      relationshipCapability: _relationshipCapability(
        targetPersonaId: profile.personaId,
        following: _followingPersonaIds.contains(profile.personaId),
      ),
    );
  }
}

/// 新增测试只引用这个对象级名称；旧 `MockUserProfileRepository` 仅供存量用例
/// 逐步迁移，避免把同一个 Persona/Profile 对象的窄 Facet 误报为新增聚合 Mock。
final class UserProfileObjectTypedDouble extends MockUserProfileRepository {
  const UserProfileObjectTypedDouble();
}

PersonaProfileViewData _profileFromAccountScenarioSeed(
  Map<String, dynamic> seed,
) {
  final ownerUserId = seed['userId']?.toString().trim() ?? '';
  if (ownerUserId.isEmpty) {
    throw const FormatException(
      'user_profile_core profile requires canonical userId',
    );
  }
  return _profileFromScenarioSeed(
    seed,
    fallbackPersonaId: FixtureUserResolver.resolvePersonaId(ownerUserId),
  );
}

PersonaProfileViewData _profileFromScenarioSeed(
  Map<String, dynamic>? seed, {
  required String fallbackPersonaId,
}) {
  final map = seed ?? const <String, dynamic>{};
  final personaId = (map['personaId'] ?? fallbackPersonaId).toString();
  final displayName = (map['displayName'] ?? personaId).toString();
  return PersonaProfileViewData(
    personaId: personaId,
    ownerUserId: (map['ownerUserId'] ?? personaId).toString(),
    subjectType: (map['subjectType'] ?? 'account').toString(),
    userHandle: (map['userHandle'] ?? personaId).toString(),
    displayName: displayName.isEmpty ? personaId : displayName,
    avatarUrl: (map['avatarUrl'] ?? '').toString(),
    avatarVersion: _intValue(map['avatarVersion']),
    backgroundUrl: (map['backgroundUrl'] ?? '').toString(),
    bio: (map['bio'] ?? '').toString(),
    identityTags: (map['identityTags'] as List<Object?>? ?? const <Object?>[])
        .map((item) => item.toString())
        .toList(growable: false),
    followerCount: _intValue(map['followerCount']),
    followingCount: _intValue(map['followingCount']),
    postCount: _intValue(map['postCount']),
    circleCount: _intValue(map['circleCount']),
    likeCount: _intValue(map['likeCount']),
    isolationLevel: (map['isolationLevel'] ?? 'open').toString(),
    profileVisibility: (map['profileVisibility'] ?? 'public').toString(),
    inheritsFromOwner: map['inheritsFromOwner'] == true,
    overriddenFields:
        (map['overriddenFields'] as List<Object?>? ?? const <Object?>[])
            .map((item) => item.toString())
            .toList(growable: false),
    updatedAt: DateTime.utc(2026, 7, 1),
  );
}

RelationshipCapabilityViewData _relationshipCapability({
  required String targetPersonaId,
  required bool following,
}) {
  return RelationshipCapabilityViewData(
    viewerPersonaId: kMockCurrentPersonaId,
    targetPersonaId: targetPersonaId,
    relationState: following ? 'following' : 'not_following',
    canFollow: !following,
    canUnfollow: following,
    canFollowBack: false,
    canGreet: true,
    canCreateDirectConversation: true,
    canSendMessage: following,
    canOpenConversation: following,
    hasPendingGreeting: false,
    hasFormalConversation: following,
    canStartVoiceCall: following,
    canStartVideoCall: following,
    isBlocked: false,
    isBlockedBy: false,
  );
}

List<Map<String, dynamic>> _scenarioProfiles() {
  return userProfileWireExamples()
      .map((item) => _stringObjectMap(item).cast<String, dynamic>())
      .toList(growable: false);
}

AuthorImpactItem _authorImpactItemFromScenarioSeed(Map<String, Object?> map) {
  final primaryText = (map['primaryText'] ?? '').toString();
  return AuthorImpactItem(
    impactId: (map['impactId'] ?? '').toString(),
    helpType: (map['helpType'] ?? '').toString(),
    action: (map['action'] ?? '').toString(),
    intersectionDimension: (map['intersectionDimension'] ?? '').toString(),
    tagRef: (map['tagRef'] ?? '').toString(),
    source: (map['source'] ?? '').toString(),
    count: _intValue(map['count']),
    primaryText: primaryText,
    subtitleText: (map['subtitleText'] ?? '').toString(),
    primarySpans: _intersectionSpans(map['primarySpans']),
    sampleVisuals: _intersectionVisuals(map['sampleVisuals']),
    representativeActor: _representativeActor(map['representativeActor']),
    actionHints: const <IntersectionActionHint>[],
    countTarget: _intersectionTarget(map['countTarget']),
    evidenceSnapshotId: (map['evidenceSnapshotId'] ?? '').toString(),
    countObjectKind: (map['countObjectKind'] ?? '').toString(),
    iconKey: (map['iconKey'] ?? '').toString(),
    freshAt: DateTime.parse(
      (map['freshAt'] ?? '2026-07-01T00:00:00Z').toString(),
    ),
    timeBucket: (map['timeBucket'] ?? '').toString(),
    lifecycleState: (map['lifecycleState'] ?? 'active').toString(),
    previousStrength: _doubleValue(map['previousStrength']),
    strengthDelta: _doubleValue(map['strengthDelta']),
  );
}

List<AuthorImpactEvidenceItem> _evidenceRows(AuthorImpactItem item) {
  final count = item.count.clamp(0, 12);
  return List<AuthorImpactEvidenceItem>.generate(count, (index) {
    final visual = index < item.sampleVisuals.length
        ? item.sampleVisuals[index]
        : null;
    return AuthorImpactEvidenceItem(
      evidenceId: '${item.impactId}_$index',
      impactId: item.impactId,
      helpType: item.helpType,
      action: item.action,
      intersectionDimension: item.intersectionDimension,
      occurredAt: item.freshAt.subtract(Duration(hours: index)).toUtc(),
      summaryText: item.primaryText,
      sampleVisual: visual,
      representativeActor: item.representativeActor,
      actionHints: item.actionHints,
      contentTarget: item.countTarget,
    );
  });
}

List<IntersectionTextSpan> _intersectionSpans(Object? raw) {
  if (raw is! List<Object?>) return const <IntersectionTextSpan>[];
  return raw
      .whereType<Map<Object?, Object?>>()
      .map((item) {
        final map = _stringObjectMap(item);
        return IntersectionTextSpan(
          text: (map['text'] ?? '').toString(),
          role: (map['role'] ?? 'plain').toString(),
          target: _intersectionTarget(map['target']),
        );
      })
      .toList(growable: false);
}

List<IntersectionVisual> _intersectionVisuals(Object? raw) {
  if (raw is! List<Object?>) return const <IntersectionVisual>[];
  return raw
      .whereType<Map<Object?, Object?>>()
      .map((item) {
        final map = _stringObjectMap(item);
        return IntersectionVisual(
          assetKind: (map['assetKind'] ?? '').toString(),
          imageUrl: (map['imageUrl'] ?? '').toString(),
          displayName: (map['displayName'] ?? '').toString(),
          target: _intersectionTarget(map['target']),
        );
      })
      .toList(growable: false);
}

IntersectionRepresentativeActor? _representativeActor(Object? raw) {
  if (raw is! Map<Object?, Object?>) return null;
  final map = _stringObjectMap(raw);
  return IntersectionRepresentativeActor(
    actorId: (map['actorId'] ?? '').toString(),
    displayName: (map['displayName'] ?? '').toString(),
    avatarUrl: (map['avatarUrl'] ?? '').toString(),
    relationLabel: (map['relationLabel'] ?? '').toString(),
    privacyState: (map['privacyState'] ?? 'visible').toString(),
    target: _intersectionTarget(map['target']),
    evidenceRank: _intValue(map['evidenceRank']),
    snapshotVersion: (map['snapshotVersion'] ?? '').toString(),
  );
}

IntersectionTarget? _intersectionTarget(Object? raw) {
  if (raw is! Map<Object?, Object?>) return null;
  final map = _stringObjectMap(raw);
  return IntersectionTarget(
    objectType: (map['objectType'] ?? '').toString(),
    objectId: (map['objectId'] ?? '').toString(),
    objectKind: (map['objectKind'] ?? '').toString(),
    routeId: (map['routeId'] ?? '').toString(),
  );
}

CursorPage<ProfileSocialRelationRowViewData> _page(
  List<ProfileSocialRelationRowViewData> source, {
  required String? query,
  required String? cursor,
  required int limit,
}) {
  final normalized = query?.trim().toLowerCase() ?? '';
  final filtered = normalized.isEmpty
      ? source
      : source
            .where(
              (item) =>
                  item.displayName.toLowerCase().contains(normalized) ||
                  item.userHandle.toLowerCase().contains(normalized),
            )
            .toList(growable: false);
  final parsedStart = int.tryParse(cursor ?? '') ?? 0;
  final start = parsedStart.clamp(0, filtered.length);
  final safeLimit = limit <= 0
      ? PersonaRelationshipListQuery.defaultLimit
      : limit;
  final end = (start + safeLimit).clamp(start, filtered.length);
  return CursorPage<ProfileSocialRelationRowViewData>(
    items: filtered.sublist(start, end),
    nextCursor: end < filtered.length ? '$end' : null,
    totalCount: filtered.length,
  );
}

Map<String, Object?> _stringObjectMap(Map<Object?, Object?> raw) {
  return raw.map((key, value) => MapEntry(key.toString(), value));
}

int _intValue(Object? value) => value is num ? value.toInt() : 0;

double _doubleValue(Object? value) => value is num ? value.toDouble() : 0;

Map<String, Object?>? _authorImpactWireExample(String authorId) {
  if (authorId != 'fixture_user_current' &&
      authorId != 'fixture_user_travel_curator') {
    return null;
  }
  final items = List<Map<String, Object?>>.generate(5, (index) {
    final primaryText = '读者${index + 1}因你的内容获得帮助';
    return <String, Object?>{
      'impactId': 'impact_${authorId}_$index',
      'helpType': <String>[
        'community',
        'decision',
        'spread',
        'relationship',
        'knowledge',
      ][index],
      'action': 'view',
      'intersectionDimension': <String>[
        'interest',
        'location',
        'content',
        'relationship',
        'content',
      ][index],
      'tagRef': 'tag/user-account/$index',
      'source': 'content',
      'count': index + 1,
      'primaryText': primaryText,
      'subtitleText': 'user_account 对象级影响证据',
      'primarySpans': <Map<String, Object?>>[
        <String, Object?>{'text': primaryText, 'role': 'plain'},
      ],
      'representativeActor': const <String, Object?>{
        'actorId': 'fixture_user_friend',
        'displayName': '契约好友',
        'relationLabel': '读者',
        'privacyState': 'visible',
        'evidenceRank': 1,
        'snapshotVersion': 'user-account-impact',
      },
      'evidenceSnapshotId': 'impact_snapshot_${authorId}_$index',
      'countObjectKind': 'person',
      'iconKey': 'content',
      'freshAt': '2026-07-20T00:00:00Z',
      'timeBucket': 'today',
      'lifecycleState': index.isEven ? 'strengthened' : 'reactivated',
      'previousStrength': 0.7,
      'strengthDelta': 0.1,
    };
  }, growable: false);
  return <String, Object?>{
    'authorId': authorId,
    'total': items.length,
    'items': items,
  };
}
