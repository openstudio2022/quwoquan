package persistence

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"

	sessionports "quwoquan_service/services/user-service/internal/account/account_session/domain/ports"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

var _ bindingapp.FederatedPhoneBindingStore = (*PostgresStore)(nil)

const federatedBindingOTPMaxAttempts = 5

func (store *PostgresStore) IssueFederatedPhoneBindingTicket(
	ctx context.Context,
	command bindingapp.IssueFederatedPhoneBindingTicket,
) (bindingapp.IssuedFederatedPhoneBindingTicket, error) {
	if store == nil || store.pool == nil {
		return bindingapp.IssuedFederatedPhoneBindingTicket{},
			errors.New("federated phone binding store unavailable")
	}
	expectedProvider, err := bindingmodel.ProviderForCredentialType(
		command.CredentialType,
	)
	if err != nil || expectedProvider != command.Provider {
		return bindingapp.IssuedFederatedPhoneBindingTicket{},
			bindingapp.ErrFederatedBindingTicketInvalid
	}
	now := time.Now().UTC()
	if command.ExpiresAt.IsZero() {
		command.ExpiresAt = now.Add(bindingapp.FederatedPhoneBindingTicketTTL)
	}

	for attempt := 0; attempt < 3; attempt++ {
		opaque, ticketID, generateErr := generateFederatedBindingTicketIdentity()
		if generateErr != nil {
			return bindingapp.IssuedFederatedPhoneBindingTicket{}, generateErr
		}
		ticket, restoreErr := bindingmodel.RestoreFederatedPhoneBindingTicket(
			bindingmodel.FederatedPhoneBindingTicket{
				ID:               ticketID,
				Hash:             federatedBindingTicketHash(opaque),
				Provider:         command.Provider,
				CredentialType:   command.CredentialType,
				CredentialKey:    strings.TrimSpace(command.CredentialKey),
				DisplayName:      strings.TrimSpace(command.DisplayName),
				AvatarURL:        strings.TrimSpace(command.AvatarURL),
				DeviceID:         strings.TrimSpace(command.DeviceID),
				Platform:         strings.TrimSpace(command.Platform),
				AppVersion:       strings.TrimSpace(command.AppVersion),
				AgreementVersion: strings.TrimSpace(command.AgreementVersion),
				PrivacyVersion:   strings.TrimSpace(command.PrivacyVersion),
				Status:           bindingmodel.FederatedPhoneBindingTicketPending,
				ExpiresAt:        command.ExpiresAt.UTC(),
				Version:          1,
				CreatedAt:        now,
				UpdatedAt:        now,
			},
		)
		if restoreErr != nil {
			return bindingapp.IssuedFederatedPhoneBindingTicket{},
				bindingapp.ErrFederatedBindingTicketInvalid
		}
		_, insertErr := store.pool.Exec(ctx, `
INSERT INTO federated_phone_binding_tickets(
  ticket_id, ticket_hash, provider, credential_type, credential_key,
  display_name, avatar_url, device_id, platform, app_version,
  agreement_version, privacy_version, status, expires_at, consumed_at,
  version, created_at, updated_at
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,NULL,$15,$16,$17
)`,
			ticket.ID,
			ticket.Hash,
			ticket.Provider,
			ticket.CredentialType,
			ticket.CredentialKey,
			ticket.DisplayName,
			ticket.AvatarURL,
			ticket.DeviceID,
			ticket.Platform,
			ticket.AppVersion,
			ticket.AgreementVersion,
			ticket.PrivacyVersion,
			ticket.Status,
			ticket.ExpiresAt,
			ticket.Version,
			ticket.CreatedAt,
			ticket.UpdatedAt,
		)
		if insertErr == nil {
			return bindingapp.IssuedFederatedPhoneBindingTicket{
				Opaque:           opaque,
				Provider:         ticket.Provider,
				ExpiresInSeconds: int(time.Until(ticket.ExpiresAt).Seconds()),
			}, nil
		}
		if !isFederatedBindingUniqueViolation(insertErr) {
			return bindingapp.IssuedFederatedPhoneBindingTicket{},
				fmt.Errorf("persist federated phone binding ticket: %w", insertErr)
		}
	}
	return bindingapp.IssuedFederatedPhoneBindingTicket{},
		errors.New("federated phone binding ticket identity collision")
}

func (store *PostgresStore) ResolveFederatedPhoneBindingTicket(
	ctx context.Context,
	opaque string,
) (bindingmodel.FederatedPhoneBindingTicket, error) {
	if !validFederatedBindingOpaque(opaque) {
		return bindingmodel.FederatedPhoneBindingTicket{},
			bindingapp.ErrFederatedBindingTicketInvalid
	}
	ticket, err := scanFederatedBindingTicket(store.pool.QueryRow(ctx, `
SELECT
  ticket_id, ticket_hash, provider, credential_type, credential_key,
  display_name, avatar_url, device_id, platform, app_version,
  agreement_version, privacy_version, status, expires_at, consumed_at,
  version, created_at, updated_at
FROM federated_phone_binding_tickets
WHERE ticket_hash=$1`, federatedBindingTicketHash(opaque)))
	if errors.Is(err, pgx.ErrNoRows) {
		return bindingmodel.FederatedPhoneBindingTicket{},
			bindingapp.ErrFederatedBindingTicketInvalid
	}
	if err != nil {
		return bindingmodel.FederatedPhoneBindingTicket{}, err
	}
	if ticket.Status == bindingmodel.FederatedPhoneBindingTicketConsumed {
		return bindingmodel.FederatedPhoneBindingTicket{},
			bindingapp.ErrFederatedBindingTicketConsumed
	}
	if !time.Now().UTC().Before(ticket.ExpiresAt) {
		return bindingmodel.FederatedPhoneBindingTicket{},
			bindingapp.ErrFederatedBindingTicketExpired
	}
	return ticket, nil
}

func (store *PostgresStore) CommitFederatedPhoneBinding(
	ctx context.Context,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) (bindingapp.FederatedPhoneBindingCompletion, error) {
	if err := validateFederatedBindingPacket(packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{IsoLevel: pgx.Serializable})
	if err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{},
			fmt.Errorf("begin federated phone binding completion: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	ticket, err := scanFederatedBindingTicket(tx.QueryRow(ctx, `
SELECT
  ticket_id, ticket_hash, provider, credential_type, credential_key,
  display_name, avatar_url, device_id, platform, app_version,
  agreement_version, privacy_version, status, expires_at, consumed_at,
  version, created_at, updated_at
FROM federated_phone_binding_tickets
WHERE ticket_hash=$1
FOR UPDATE`, federatedBindingTicketHash(packet.OpaqueTicket)))
	if errors.Is(err, pgx.ErrNoRows) {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingTicketInvalid
	}
	if err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if !sameFederatedBindingTicket(ticket, packet.ExpectedTicket) {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingVersion
	}
	if ticket.Status != bindingmodel.FederatedPhoneBindingTicketPending {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingTicketConsumed
	}
	if !packet.OccurredAt.Before(ticket.ExpiresAt) {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingTicketExpired
	}
	if !ticket.MatchesContext(
		packet.DeviceID,
		packet.Platform,
		packet.AppVersion,
		packet.AgreementVersion,
		packet.PrivacyVersion,
	) {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingContext
	}

	challenge, err := lockFederatedBindingChallenge(ctx, tx, packet.ChallengeID)
	if errors.Is(err, pgx.ErrNoRows) {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingOTPExpired
	}
	if err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if challenge.purpose != "bind_phone" ||
		challenge.channel != "sms" ||
		challenge.destinationHash != packet.PhoneDestinationHash ||
		challenge.bindingTicketID != ticket.ID {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingContext
	}
	if err := validateFederatedBindingChallengeState(challenge, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if !constantTimeTextEqual(challenge.secretRef, packet.OTPSecretRef) {
		challenge.attemptCount++
		status := challengemodel.StatusPending
		failure := bindingapp.ErrFederatedBindingOTPMismatch
		if challenge.attemptCount >= packet.OTPMaxAttempts {
			status = challengemodel.StatusLocked
			failure = bindingapp.ErrFederatedBindingOTPLocked
		}
		if _, updateErr := tx.Exec(ctx, `
UPDATE authentication_challenges
SET status=$2, failed_attempts=$3, version=version+1, updated_at=$4
WHERE challenge_id=$1 AND version=$5`,
			packet.ChallengeID,
			status,
			challenge.attemptCount,
			packet.OccurredAt,
			challenge.version,
		); updateErr != nil {
			return bindingapp.FederatedPhoneBindingCompletion{}, updateErr
		}
		if commitErr := tx.Commit(ctx); commitErr != nil {
			return bindingapp.FederatedPhoneBindingCompletion{}, commitErr
		}
		return bindingapp.FederatedPhoneBindingCompletion{}, failure
	}

	if err := lockFederatedBindingCredentialCoordinates(ctx, tx, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	ownerID := packet.ExpectedOwnerID
	conflict, conflictErr := federatedBindingNewAccountConflict(
		ctx,
		tx,
		packet.Phone,
		ticket,
	)
	if conflictErr != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, conflictErr
	}
	if conflict {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingConflict
	}
	if err := insertFederatedBindingProfile(ctx, tx, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, mapFederatedBindingWriteError(err)
	}
	if err := insertFederatedBindingPersona(ctx, tx, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, mapFederatedBindingWriteError(err)
	}
	if err := insertFederatedBindingPersonaPacket(ctx, tx, ticket, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, mapFederatedBindingWriteError(err)
	}
	if err := insertFederatedBindingCredential(ctx, tx, *packet.PhoneBinding); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, mapFederatedBindingWriteError(err)
	}
	if err := insertFederatedBindingCredential(ctx, tx, packet.SocialBinding); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, mapFederatedBindingWriteError(err)
	}
	if err := insertFederatedBindingDevice(ctx, tx, ownerID, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if err := insertFederatedBindingConsent(ctx, tx, ownerID, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if err := insertFederatedBindingSession(ctx, tx, ownerID, packet); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}

	challengeTag, err := tx.Exec(ctx, `
UPDATE authentication_challenges
SET status='completed', consumed_at=$2, completion_fingerprint=$3,
    version=version+1, updated_at=$2
WHERE challenge_id=$1 AND version=$4 AND status='pending'`,
		packet.ChallengeID,
		packet.OccurredAt,
		packet.OTPCompletionDigest,
		challenge.version,
	)
	if err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if challengeTag.RowsAffected() != 1 {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingVersion
	}
	ticketTag, err := tx.Exec(ctx, `
UPDATE federated_phone_binding_tickets
SET status='consumed', consumed_at=$2, version=version+1, updated_at=$2
WHERE ticket_id=$1 AND version=$3 AND status='pending'`,
		ticket.ID,
		packet.OccurredAt,
		ticket.Version,
	)
	if err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{}, err
	}
	if ticketTag.RowsAffected() != 1 {
		return bindingapp.FederatedPhoneBindingCompletion{},
			bindingapp.ErrFederatedBindingVersion
	}
	if err := tx.Commit(ctx); err != nil {
		return bindingapp.FederatedPhoneBindingCompletion{},
			mapFederatedBindingWriteError(err)
	}
	return bindingapp.FederatedPhoneBindingCompletion{
		OwnerID:        ownerID,
		PersonaID:      packet.ExpectedPersonaID,
		PersonaVersion: packet.ExpectedPersonaVer,
	}, nil
}

type federatedBindingChallenge struct {
	purpose          string
	channel          string
	destinationHash  string
	secretRef        string
	bindingTicketID  string
	status           challengemodel.Status
	attemptCount     int
	expiresAt        time.Time
	completionDigest string
	version          int64
}

func lockFederatedBindingChallenge(
	ctx context.Context,
	tx pgx.Tx,
	challengeID string,
) (federatedBindingChallenge, error) {
	var challenge federatedBindingChallenge
	err := tx.QueryRow(ctx, `
SELECT
  purpose, channel, COALESCE(phone_hash, ''), code_hash,
  COALESCE(binding_ticket_id, ''), status, failed_attempts, expires_at,
  COALESCE(completion_fingerprint, ''), version
FROM authentication_challenges
WHERE challenge_id=$1
FOR UPDATE`, strings.TrimSpace(challengeID)).Scan(
		&challenge.purpose,
		&challenge.channel,
		&challenge.destinationHash,
		&challenge.secretRef,
		&challenge.bindingTicketID,
		&challenge.status,
		&challenge.attemptCount,
		&challenge.expiresAt,
		&challenge.completionDigest,
		&challenge.version,
	)
	return challenge, err
}

func validateFederatedBindingChallengeState(
	challenge federatedBindingChallenge,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	switch challenge.status {
	case challengemodel.StatusPending:
		if !packet.OccurredAt.Before(challenge.expiresAt) {
			return bindingapp.ErrFederatedBindingOTPExpired
		}
	case challengemodel.StatusLocked:
		return bindingapp.ErrFederatedBindingOTPLocked
	case challengemodel.StatusExpired, challengemodel.StatusCancelled:
		return bindingapp.ErrFederatedBindingOTPExpired
	case challengemodel.StatusCompleted:
		return bindingapp.ErrFederatedBindingOTPConsumed
	default:
		return bindingapp.ErrFederatedBindingOTPExpired
	}
	return nil
}

func validateFederatedBindingPacket(
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	if !validFederatedBindingOpaque(packet.OpaqueTicket) ||
		strings.TrimSpace(packet.ChallengeID) == "" ||
		strings.TrimSpace(packet.Phone) == "" ||
		len(strings.TrimSpace(packet.PhoneDestinationHash)) != 64 ||
		len(strings.TrimSpace(packet.OTPSecretRef)) != 64 ||
		len(strings.TrimSpace(packet.OTPCompletionDigest)) != 64 ||
		packet.OTPMaxAttempts <= 0 ||
		packet.OccurredAt.IsZero() ||
		strings.TrimSpace(packet.ConsentID) == "" ||
		strings.TrimSpace(packet.DeviceRegistrationID) == "" ||
		strings.TrimSpace(packet.Session.SessionID) == "" ||
		strings.TrimSpace(packet.Session.LineageID) == "" ||
		len(strings.TrimSpace(packet.Session.RefreshTokenHash)) != 64 ||
		strings.TrimSpace(packet.Session.AuthenticationSubject) == "" ||
		strings.TrimSpace(packet.Session.IdentityOrigin) == "" ||
		packet.Session.ExpiresAt.IsZero() ||
		strings.TrimSpace(packet.Session.OutboxEventID) == "" {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	if packet.NewAccount == nil || packet.PhoneBinding == nil {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	if _, err := bindingmodel.RestoreFederatedPhoneBindingTicket(
		packet.ExpectedTicket,
	); err != nil {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	socialEvent, err := validateBindChange(packet.SocialBinding)
	if err != nil || socialEvent.Type != bindingmodel.CredentialBoundEvent {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	ownerID := strings.TrimSpace(packet.ExpectedOwnerID)
	socialState := packet.SocialBinding.Aggregate.State()
	if ownerID == "" || packet.ExpectedAuthEpoch <= 0 ||
		strings.TrimSpace(packet.ExpectedPersonaID) == "" ||
		packet.ExpectedPersonaVer <= 0 ||
		socialState.OwnerID != ownerID ||
		socialState.CredentialType != packet.ExpectedTicket.CredentialType ||
		socialState.CredentialKey != packet.ExpectedTicket.CredentialKey {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	if packet.NewAccount.Profile == nil || packet.NewAccount.Persona == nil {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	phoneEvent, err := validateBindChange(*packet.PhoneBinding)
	if err != nil || phoneEvent.Type != bindingmodel.CredentialBoundEvent {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	phoneState := packet.PhoneBinding.Aggregate.State()
	if packet.NewAccount.Profile.UserID != ownerID ||
		packet.NewAccount.Profile.Phone != packet.Phone ||
		int64(packet.NewAccount.Profile.AuthEpoch) != packet.ExpectedAuthEpoch ||
		packet.NewAccount.Persona.UserID != ownerID ||
		packet.NewAccount.Persona.PersonaID != packet.ExpectedPersonaID ||
		int64(packet.NewAccount.Persona.Version) != packet.ExpectedPersonaVer ||
		phoneState.OwnerID != ownerID ||
		phoneState.CredentialType != bindingmodel.CredentialTypePhone ||
		phoneState.CredentialKey != packet.Phone {
		return bindingapp.ErrFederatedBindingTicketInvalid
	}
	return nil
}

func insertFederatedBindingProfile(
	ctx context.Context,
	tx pgx.Tx,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	profile := packet.NewAccount.Profile
	profile.CreatedAt = packet.OccurredAt
	profile.UpdatedAt = packet.OccurredAt
	_, err := tx.Exec(ctx, `
INSERT INTO user_profiles (
  user_id, account_state, auth_epoch, identity_origin, logical_shard,
  anonymous_retention_policy, phone, nickname, nickname_customized,
  avatar_version, profile_version, persona_count, created_at, updated_at
) VALUES (
  $1,$2,$3,$4,$5,$6,$7,'',false,0,0,$8,$9,$9
)`,
		profile.UserID,
		profile.AccountState,
		profile.AuthEpoch,
		profile.IdentityOrigin,
		profile.LogicalShard,
		profile.AnonymousRetentionPolicy,
		profile.Phone,
		profile.PersonaCount,
		packet.OccurredAt,
	)
	return err
}

func insertFederatedBindingPersona(
	ctx context.Context,
	tx pgx.Tx,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	persona := packet.NewAccount.Persona
	persona.CreatedAt = packet.OccurredAt
	persona.UpdatedAt = packet.OccurredAt
	_, err := tx.Exec(ctx, `
INSERT INTO personas (
  persona_id, user_id, display_name, nickname_customized, user_handle, bio,
  identity_tags, taxonomy_release_id, gender, birth_date, region, region_tag_ref,
  avatar_media_asset_id, avatar_url, avatar_version,
  background_media_asset_id, background_url, caller_ringtone_id,
  theme_mode_override, font_size_preset_override,
  appearance_override_updated_at, is_primary, is_private, is_active,
  isolation_level, purpose_hint, status, retired_at,
  inherits_profile_from_owner, overridden_profile_fields,
  last_profile_sync_at, last_profile_sync_source, last_activated_at,
  version, created_at, updated_at
) VALUES (
  $1,$2,$3,$4,NULLIF($5,''),$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
  $17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,
  $33,$34,$35,$36
)`,
		persona.PersonaID,
		persona.UserID,
		persona.DisplayName,
		persona.NicknameCustomized,
		persona.UserHandle,
		persona.Bio,
		persona.IdentityTags,
		persona.TaxonomyReleaseID,
		persona.Gender,
		persona.BirthDate,
		persona.Region,
		persona.RegionTagRef,
		persona.AvatarMediaAssetID,
		persona.AvatarURL,
		persona.AvatarVersion,
		persona.BackgroundMediaAssetID,
		persona.BackgroundURL,
		persona.CallerRingtoneID,
		persona.ThemeModeOverride,
		persona.FontSizePresetOverride,
		persona.AppearanceOverrideUpdatedAt,
		persona.IsPrimary,
		persona.IsPrivate,
		persona.IsActive,
		persona.IsolationLevel,
		persona.PurposeHint,
		persona.Status,
		persona.RetiredAt,
		persona.InheritsProfileFromOwner,
		persona.OverriddenProfileFields,
		persona.LastProfileSyncAt,
		persona.LastProfileSyncSource,
		persona.LastActivatedAt,
		persona.Version,
		persona.CreatedAt,
		persona.UpdatedAt,
	)
	return err
}

func insertFederatedBindingPersonaPacket(
	ctx context.Context,
	tx pgx.Tx,
	ticket bindingmodel.FederatedPhoneBindingTicket,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	persona := packet.NewAccount.Persona
	idempotencyKey := "federated-persona-bootstrap:" + ticket.ID
	commandDigestBytes := sha256.Sum256([]byte(strings.Join([]string{
		packet.ExpectedOwnerID,
		persona.PersonaID,
		fmt.Sprintf("%d", persona.Version),
	}, "\x00")))
	commandDigest := hex.EncodeToString(commandDigestBytes[:])
	eventID := stableFederatedPersonaPacketID("event", idempotencyKey)
	receiptID := stableFederatedPersonaPacketID("receipt", idempotencyKey)
	payload, err := json.Marshal(map[string]string{
		"userId":    packet.ExpectedOwnerID,
		"personaId": persona.PersonaID,
	})
	if err != nil {
		return err
	}
	result, err := json.Marshal(bindingapp.FederatedPhoneBindingCompletion{
		OwnerID:        packet.ExpectedOwnerID,
		PersonaID:      persona.PersonaID,
		PersonaVersion: int64(persona.Version),
	})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,'PersonaCreated',$4,$5)`,
		eventID, persona.PersonaID, persona.Version, payload, packet.OccurredAt,
	); err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `
INSERT INTO personas_command_receipts(
  receipt_id, aggregate_id, idempotency_key, command_digest,
  aggregate_version, result_json, created_at
) VALUES ($1,$2,$3,$4,$5,$6,$7)`,
		receiptID, persona.PersonaID, idempotencyKey, commandDigest,
		persona.Version, result, packet.OccurredAt,
	)
	return err
}

func stableFederatedPersonaPacketID(kind string, idempotencyKey string) string {
	digest := sha256.Sum256([]byte(kind + "\x00" + idempotencyKey))
	return "pp_" + hex.EncodeToString(digest[:24])
}

func insertFederatedBindingCredential(
	ctx context.Context,
	tx pgx.Tx,
	change bindingmodel.ChangeSet,
) error {
	event, err := validateBindChange(change)
	if err != nil {
		return err
	}
	state := change.Aggregate.State()
	tag, err := tx.Exec(ctx, `
INSERT INTO credential_bindings(
  id, owner_id, credential_type, credential_key, display_label,
  is_active, bound_at, last_used_at, version
) VALUES ($1,$2,$3,$4,NULLIF($5,''),true,$6,$7,$8)
ON CONFLICT DO NOTHING`,
		state.ID,
		state.OwnerID,
		state.CredentialType,
		state.CredentialKey,
		state.DisplayLabel,
		state.BoundAt,
		state.LastUsedAt,
		state.Version,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return bindingapp.ErrFederatedBindingConflict
	}
	return appendSecurityOutbox(ctx, tx, event)
}

func insertFederatedBindingDevice(
	ctx context.Context,
	tx pgx.Tx,
	ownerID string,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	_, err := tx.Exec(ctx, `
INSERT INTO user_devices(
  id, account_id, device_id, app_version, status, version,
  last_active_at, created_at, updated_at
) VALUES ($1,$2,$3,NULLIF($4,''),'active',1,$5,$5,$5)
ON CONFLICT (account_id, device_id) DO UPDATE SET
  app_version=EXCLUDED.app_version,
  status='active',
  version=user_devices.version+1,
  last_active_at=EXCLUDED.last_active_at,
  updated_at=EXCLUDED.updated_at`,
		packet.DeviceRegistrationID,
		ownerID,
		packet.DeviceID,
		packet.AppVersion,
		packet.OccurredAt,
	)
	return err
}

func insertFederatedBindingConsent(
	ctx context.Context,
	tx pgx.Tx,
	ownerID string,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	_, err := tx.Exec(ctx, `
INSERT INTO consent_records(
  id, owner_id, agreement_version, privacy_version, accepted_at,
  device_id, platform, source_operation
) VALUES ($1,$2,$3,$4,$5,$6,$7,'CompleteFederatedPhoneBinding')`,
		packet.ConsentID,
		ownerID,
		packet.AgreementVersion,
		packet.PrivacyVersion,
		packet.OccurredAt,
		packet.DeviceID,
		packet.Platform,
	)
	return err
}

func insertFederatedBindingSession(
	ctx context.Context,
	tx pgx.Tx,
	ownerID string,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	session := packet.Session
	_, err := tx.Exec(ctx, `
INSERT INTO account_sessions(
  session_id, account_id, device_id, refresh_token_hash, lineage_id,
  status, issued_at, expires_at, version, created_at, updated_at
) VALUES ($1,$2,$3,$4,$5,'active',$6,$7,1,$6,$6)`,
		session.SessionID,
		ownerID,
		packet.DeviceID,
		session.RefreshTokenHash,
		session.LineageID,
		packet.OccurredAt,
		session.ExpiresAt,
	)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(map[string]any{
		"sessionId":             session.SessionID,
		"accountId":             ownerID,
		"deviceId":              packet.DeviceID,
		"lineageId":             session.LineageID,
		"authenticationSubject": session.AuthenticationSubject,
		"identityOrigin":        session.IdentityOrigin,
		"issuedAt":              packet.OccurredAt,
	})
	if err != nil {
		return err
	}
	_, err = tx.Exec(ctx, `
INSERT INTO account_sessions_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,1,$3,$4,$5)`,
		session.OutboxEventID,
		session.SessionID,
		sessionports.AccountSessionAuthenticatedEvent,
		payload,
		packet.OccurredAt,
	)
	return err
}

func lockFederatedBindingCredentialCoordinates(
	ctx context.Context,
	tx pgx.Tx,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) error {
	keys := []string{
		"credential:phone:" + packet.Phone,
		"credential:" + string(packet.ExpectedTicket.CredentialType) + ":" +
			packet.ExpectedTicket.CredentialKey,
		"credential-owner:" + packet.ExpectedOwnerID + ":" +
			string(packet.ExpectedTicket.CredentialType),
	}
	sort.Strings(keys)
	for index, key := range keys {
		if index > 0 && key == keys[index-1] {
			continue
		}
		if _, err := tx.Exec(ctx, `
SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`, key); err != nil {
			return fmt.Errorf("lock federated credential coordinate: %w", err)
		}
	}
	return nil
}

func federatedBindingNewAccountConflict(
	ctx context.Context,
	tx pgx.Tx,
	phone string,
	ticket bindingmodel.FederatedPhoneBindingTicket,
) (bool, error) {
	var exists bool
	err := tx.QueryRow(ctx, `
SELECT EXISTS(
  SELECT 1 FROM credential_bindings
  WHERE (credential_type='phone' AND credential_key=$1)
     OR (credential_type=$2 AND credential_key=$3)
) OR EXISTS(
  SELECT 1 FROM user_profiles WHERE phone=$1
	)`, phone, ticket.CredentialType, ticket.CredentialKey).Scan(&exists)
	return exists, err
}

func scanFederatedBindingTicket(row pgx.Row) (
	bindingmodel.FederatedPhoneBindingTicket,
	error,
) {
	var ticket bindingmodel.FederatedPhoneBindingTicket
	err := row.Scan(
		&ticket.ID,
		&ticket.Hash,
		&ticket.Provider,
		&ticket.CredentialType,
		&ticket.CredentialKey,
		&ticket.DisplayName,
		&ticket.AvatarURL,
		&ticket.DeviceID,
		&ticket.Platform,
		&ticket.AppVersion,
		&ticket.AgreementVersion,
		&ticket.PrivacyVersion,
		&ticket.Status,
		&ticket.ExpiresAt,
		&ticket.ConsumedAt,
		&ticket.Version,
		&ticket.CreatedAt,
		&ticket.UpdatedAt,
	)
	if err != nil {
		return bindingmodel.FederatedPhoneBindingTicket{}, err
	}
	return bindingmodel.RestoreFederatedPhoneBindingTicket(ticket)
}

func sameFederatedBindingTicket(
	left bindingmodel.FederatedPhoneBindingTicket,
	right bindingmodel.FederatedPhoneBindingTicket,
) bool {
	return left.ID == right.ID &&
		constantTimeTextEqual(left.Hash, right.Hash) &&
		left.Provider == right.Provider &&
		left.CredentialType == right.CredentialType &&
		constantTimeTextEqual(left.CredentialKey, right.CredentialKey) &&
		left.DeviceID == right.DeviceID &&
		left.Platform == right.Platform &&
		left.AppVersion == right.AppVersion &&
		left.AgreementVersion == right.AgreementVersion &&
		left.PrivacyVersion == right.PrivacyVersion &&
		left.Status == right.Status &&
		left.Version == right.Version &&
		left.ExpiresAt.Equal(right.ExpiresAt)
}

func generateFederatedBindingTicketIdentity() (string, string, error) {
	randomBytes := make([]byte, 32)
	if _, err := rand.Read(randomBytes); err != nil {
		return "", "", err
	}
	opaque := "fb_" + base64.RawURLEncoding.EncodeToString(randomBytes)
	ticketID, err := randomFederatedBindingID("fbt_")
	return opaque, ticketID, err
}

func randomFederatedBindingID(prefix string) (string, error) {
	randomBytes := make([]byte, 16)
	if _, err := rand.Read(randomBytes); err != nil {
		return "", err
	}
	return prefix + hex.EncodeToString(randomBytes), nil
}

func federatedBindingTicketHash(opaque string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(opaque)))
	return hex.EncodeToString(digest[:])
}

func validFederatedBindingOpaque(opaque string) bool {
	opaque = strings.TrimSpace(opaque)
	return strings.HasPrefix(opaque, "fb_") && len(opaque) >= 40 && len(opaque) <= 96
}

func constantTimeTextEqual(left string, right string) bool {
	leftBytes := []byte(strings.TrimSpace(left))
	rightBytes := []byte(strings.TrimSpace(right))
	return len(leftBytes) == len(rightBytes) &&
		subtle.ConstantTimeCompare(leftBytes, rightBytes) == 1
}

func isFederatedBindingUniqueViolation(err error) bool {
	var pgError *pgconn.PgError
	return errors.As(err, &pgError) && pgError.Code == "23505"
}

func mapFederatedBindingWriteError(err error) error {
	if errors.Is(err, bindingapp.ErrFederatedBindingConflict) ||
		isFederatedBindingUniqueViolation(err) {
		return bindingapp.ErrFederatedBindingConflict
	}
	return err
}
