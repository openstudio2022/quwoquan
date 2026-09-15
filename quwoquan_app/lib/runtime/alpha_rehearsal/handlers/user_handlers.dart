import 'dart:convert';

import 'package:quwoquan_app/runtime/alpha_rehearsal/kernel/rehearsal_ports.dart';
import 'package:quwoquan_app/runtime/auth/rehearsal_auth_port.dart';
import 'package:quwoquan_app/runtime/errors/content_capability_unavailable.dart';
import 'package:quwoquan_app/runtime/errors/local_domain_failure.dart';

part 'user_account_handler_part.dart';
part 'user_relationship_handler_part.dart';
part 'user_persona_handler_part.dart';

enum UserRehearsalCapabilityStatus { supported, unsupported }

final class UserRehearsalCapability {
  const UserRehearsalCapability.supported(this.canonicalOperationId)
    : status = UserRehearsalCapabilityStatus.supported,
      blocker = null;
  const UserRehearsalCapability.unsupported(
    this.canonicalOperationId,
    this.blocker,
  ) : status = UserRehearsalCapabilityStatus.unsupported;

  final String canonicalOperationId;
  final UserRehearsalCapabilityStatus status;
  final String? blocker;
}

/// Alpha user 域的真实能力清单；registry 只能从 supported 集合登记 dispatch。
final Map<String, UserRehearsalCapability> userRehearsalCapabilities = {
  for (final id in _supportedUserOperations)
    id: UserRehearsalCapability.supported(id),
  for (final id in _externalProviderOperations)
    id: UserRehearsalCapability.unsupported(id, 'external_identity_provider'),
};

const Set<String> _externalProviderOperations = {
  'user.account_session.LoginOneTap',
  'user.account_session.LoginWithAlipay',
  'user.account_session.LoginWithQq',
  'user.account_session.LoginWithWechat',
  'user.authentication_challenge.CreateAlipayAuthorizationRequest',
  'user.authentication_challenge.ResolveOneTapLoginHint',
  'user.credential_binding.BindCarrierPhoneCredential',
  'user.credential_binding.CompleteFederatedPhoneBinding',
};

const Set<String> _supportedUserOperations = {
  'user.account_session.LoginAnonymous',
  'user.account_session.LoginWithPhone',
  'user.account_session.Logout',
  'user.account_session.RefreshToken',
  'user.authentication_challenge.SendOtp',
  'user.authentication_challenge.GetOtpDeliveryReadiness',
  'user.contact_discovery_record.DismissContactDiscovery',
  'user.contact_discovery_record.GetLatestContactDiscovery',
  'user.contact_discovery_record.InitiateContactDiscovery',
  'user.credential_binding.BindPhoneCredential',
  'user.credential_binding.ListCredentials',
  'user.credential_binding.UnbindCredential',
  'user.device_registration.RemoveDevicePushEndpoint',
  'user.device_registration.UpsertDevicePushEndpoint',
  'user.followed_subject_visit_state.MarkFollowedSubjectVisited',
  'user.following_subject.ListFollowingSubjects',
  'user.greeting_request.CancelGreetingRequest',
  'user.greeting_request.IgnoreGreetingRequest',
  'user.greeting_request.ListGreetingInbox',
  'user.greeting_request.ListGreetingOutbox',
  'user.greeting_request.ReplyGreetingRequest',
  'user.greeting_request.SendGreetingRequest',
  'user.persona.ActivatePersona',
  'user.persona.ApplyPersonaProfileSync',
  'user.persona.CreatePersona',
  'user.persona.RetirePersona',
  'user.persona.UpdatePersona',
  'user.persona.UpdateUserProfile',
  'user.persona_relationship.BlockUser',
  'user.persona_relationship.FollowUser',
  'user.persona_relationship.GetRelationshipCapability',
  'user.persona_relationship.ListBlockedUsers',
  'user.persona_relationship.ListFollowers',
  'user.persona_relationship.ListFollowing',
  'user.persona_relationship.UnblockUser',
  'user.persona_relationship.UnfollowUser',
  'user.profile_update_proposal.CreateProfileUpdateProposal',
  'user.profile_update_proposal.GetProfileUpdateProposal',
  'user.profile_update_proposal.ListProfileUpdateProposals',
  'user.profile_update_proposal.ApplyProposal',
  'user.profile_update_proposal.ConfirmProposal',
  'user.profile_update_proposal.RejectProposal',
  'user.profile_update_proposal.RollbackProposal',
  'user.subject_follow.FollowSubject',
  'user.subject_follow.UnfollowSubject',
  'user.user_account.CloseAccount',
  'user.user_account.GetActivePersonaContext',
  'user.user_account.GetMeProfile',
  'user.user_account.GetPersonaLifecycleGuard',
  'user.user_account.GetPersonaManagementSummary',
  'user.user_account.GetPersonaProfile',
  'user.user_account.GetProfileEditSnapshot',
  'user.user_account.GetProfileQrCard',
  'user.user_account.GetUserHomepageBundle',
  'user.user_account.ListPersonas',
  'user.user_account.PullUserSync',
  'user.user_account.ResolveProfileQrToken',
  'user.user_account.SearchSocialRelations',
  'user.user_settings.GetAppearanceSettings',
  'user.user_settings.GetCallSettings',
  'user.user_settings.GetNotificationSettings',
  'user.user_settings.GetPrivacySettings',
  'user.user_settings.UpdateAppearanceSettings',
  'user.user_settings.UpdateCallSettings',
  'user.user_settings.UpdateNotificationSettings',
  'user.user_settings.UpdatePrivacySettings',
};

final class UserRehearsalHandler implements RehearsalObjectHandler {
  const UserRehearsalHandler();

  @override
  Stream<Object?>? stream(RehearsalInvocation invocation) => null;

  @override
  Future<Object?> handle(RehearsalInvocation invocation) {
    final id = invocation.operation.canonicalOperationId;
    final capability = userRehearsalCapabilities[id];
    if (capability == null ||
        capability.status == UserRehearsalCapabilityStatus.unsupported) {
      throw contentCapabilityUnavailable(
        'rehearsal_user_${capability?.blocker ?? 'operation'}',
      );
    }
    if (id.startsWith('user.account_session.') ||
        id.startsWith('user.authentication_challenge.') ||
        id.startsWith('user.contact_discovery_record.') ||
        id.startsWith('user.credential_binding.') ||
        id.startsWith('user.device_registration.') ||
        id.startsWith('user.user_settings.')) {
      return const _UserAccountHandlerPart().handle(invocation);
    }
    if (id.startsWith('user.persona_relationship.') ||
        id.startsWith('user.greeting_request.') ||
        id.startsWith('user.subject_follow.') ||
        id.startsWith('user.followed_subject_visit_state.') ||
        id.startsWith('user.following_subject.')) {
      return const _UserRelationshipHandlerPart().handle(invocation);
    }
    return const _UserPersonaHandlerPart().handle(invocation);
  }
}

Map<String, Map<String, Object?>> _records(
  RehearsalInvocation invocation,
  String name,
) => invocation.store.records.putIfAbsent(
  name,
  () => <String, Map<String, Object?>>{},
);

Map<String, Object?> _requireIdentity(RehearsalInvocation invocation) {
  invocation.requireActor();
  for (final row in invocation.store.identities.values) {
    if (row['ownerId'] == invocation.context.actor.accountId &&
        (invocation.context.actor.personaId == null ||
            row['personaId'] == invocation.context.actor.personaId)) {
      if (row['accountState'] == 'closed') {
        throw localDomainCloudException('USER.USER.account_closed');
      }
      return row;
    }
  }
  rehearsalUnauthorized();
}

Map<String, Object?> _requireOwnedPersona(
  RehearsalInvocation invocation,
  String personaId,
) {
  final identity = _requireIdentity(invocation);
  final row = _records(invocation, 'user.personas')[personaId];
  if (row == null || row['ownerId'] != identity['ownerId']) {
    rehearsalNotFound('USER.USER.persona_not_found');
  }
  return row!;
}

String _text(Map<String, Object?> body, String key, [String fallback = '']) =>
    '${body[key] ?? fallback}'.trim();

int _integer(Map<String, Object?> body, String key, [int fallback = 0]) =>
    body[key] is int ? body[key]! as int : fallback;

String _timestamp(RehearsalInvocation invocation) =>
    invocation.now().toUtc().toIso8601String();

Map<String, Object?> _page(
  RehearsalInvocation invocation,
  List<Map<String, Object?>> source, {
  int defaultLimit = 20,
}) {
  final limit =
      int.tryParse(invocation.query('limit')) ??
      _integer(invocation.body, 'limit', defaultLimit);
  final bounded = limit.clamp(1, 100);
  var offset = 0;
  final cursor = invocation.query('cursor').isNotEmpty
      ? invocation.query('cursor')
      : _text(invocation.body, 'cursor');
  if (cursor.isNotEmpty) {
    try {
      final decoded = jsonDecode(utf8.decode(base64Url.decode(cursor)));
      if (decoded is! List ||
          decoded.length != 3 ||
          decoded[0] != invocation.actorId ||
          decoded[1] != invocation.operation.canonicalOperationId ||
          decoded[2] is! int) {
        throw const FormatException();
      }
      offset = decoded[2] as int;
    } catch (_) {
      throw localDomainCloudException('USER.USER.invalid_cursor');
    }
  }
  if (offset < 0 || offset > source.length) {
    throw localDomainCloudException('USER.USER.invalid_cursor');
  }
  final end = (offset + bounded).clamp(0, source.length);
  final items = source.sublist(offset, end);
  return {
    'items': items,
    if (end < source.length)
      'nextCursor': base64Url.encode(
        utf8.encode(
          jsonEncode([
            invocation.actorId,
            invocation.operation.canonicalOperationId,
            end,
          ]),
        ),
      ),
  };
}
