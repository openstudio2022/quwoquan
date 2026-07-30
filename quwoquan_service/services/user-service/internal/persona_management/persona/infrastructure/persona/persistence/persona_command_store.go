package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// PersonaCommandPostgresStore 实现 Persona 聚合的对象专属命令提交端口：
// state、personas_command_receipts 与 personas_outbox 在同一事务原子提交，
// 同一 Idempotency-Key 重放返回首次结果。
type PersonaCommandPostgresStore struct {
	pool *pgxpool.Pool
}

func NewPersonaCommandPostgresStore(pool *pgxpool.Pool) (*PersonaCommandPostgresStore, error) {
	if pool == nil {
		return nil, errors.New("Persona command PostgreSQL pool is required")
	}
	return &PersonaCommandPostgresStore{pool: pool}, nil
}

var _ personaports.PersonaCommandStore = (*PersonaCommandPostgresStore)(nil)

func (s *PersonaCommandPostgresStore) CommitCreate(
	ctx context.Context,
	persona *usermodel.Persona,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	if persona == nil || strings.TrimSpace(persona.PersonaID) == "" {
		return personaports.PersonaCommandResult{},
			errors.New("persona create requires aggregate identity")
	}
	return s.commit(ctx, meta, func(tx pgx.Tx) (personaports.PersonaCommandResult, error) {
		now := time.Now().UTC()
		persona.CreatedAt = now
		persona.UpdatedAt = now
		persona.Version = 1
		if _, err := tx.Exec(ctx,
			`INSERT INTO personas (
persona_id, user_id, display_name, nickname_customized, user_handle,
bio, identity_tags, taxonomy_release_id, gender, birth_date, region,
region_tag_ref, avatar_media_asset_id, avatar_url, avatar_version,
background_media_asset_id, background_url, caller_ringtone_id,
theme_mode_override, font_size_preset_override, appearance_override_updated_at,
is_primary, is_private, is_active, isolation_level, purpose_hint, status,
retired_at, inherits_profile_from_owner, overridden_profile_fields,
last_profile_sync_at, last_profile_sync_source, last_activated_at, version,
created_at, updated_at
) VALUES (
$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35,$36
)`,
			persona.PersonaID, persona.UserID, persona.DisplayName,
			persona.NicknameCustomized, persona.UserHandle, persona.Bio,
			persona.IdentityTags, persona.TaxonomyReleaseID, persona.Gender,
			persona.BirthDate, persona.Region, persona.RegionTagRef,
			persona.AvatarMediaAssetID, persona.AvatarURL, persona.AvatarVersion,
			persona.BackgroundMediaAssetID, persona.BackgroundURL,
			persona.CallerRingtoneID, persona.ThemeModeOverride,
			persona.FontSizePresetOverride, persona.AppearanceOverrideUpdatedAt,
			persona.IsPrimary, persona.IsPrivate, persona.IsActive,
			persona.IsolationLevel, persona.PurposeHint, persona.Status,
			persona.RetiredAt, persona.InheritsProfileFromOwner,
			persona.OverriddenProfileFields, persona.LastProfileSyncAt,
			persona.LastProfileSyncSource, persona.LastActivatedAt, persona.Version,
			persona.CreatedAt, persona.UpdatedAt,
		); err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		return personaports.PersonaCommandResult{
				PersonaID: persona.PersonaID,
				Version:   1,
			}, s.appendPacket(ctx, tx, persona.UserID, persona.PersonaID, 1,
				personaports.PersonaCreatedEvent, meta)
	})
}

func (s *PersonaCommandPostgresStore) CommitMutation(
	ctx context.Context,
	persona *usermodel.Persona,
	eventType string,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	if persona == nil || strings.TrimSpace(persona.PersonaID) == "" {
		return personaports.PersonaCommandResult{},
			errors.New("persona mutation requires aggregate identity")
	}
	if strings.TrimSpace(eventType) == "" {
		return personaports.PersonaCommandResult{},
			errors.New("persona mutation requires event type")
	}
	return s.commit(ctx, meta, func(tx pgx.Tx) (personaports.PersonaCommandResult, error) {
		var currentVersion int64
		err := tx.QueryRow(ctx,
			`SELECT version FROM personas WHERE persona_id=$1 FOR UPDATE`,
			persona.PersonaID,
		).Scan(&currentVersion)
		if errors.Is(err, pgx.ErrNoRows) {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		nextVersion := currentVersion + 1
		persona.UpdatedAt = time.Now().UTC()
		persona.Version = int(nextVersion)
		tag, err := tx.Exec(ctx,
			`UPDATE personas SET
user_id=$2, display_name=$3, nickname_customized=$4, user_handle=$5,
bio=$6, identity_tags=$7, taxonomy_release_id=$8, gender=$9, birth_date=$10,
region=$11, region_tag_ref=$12, avatar_media_asset_id=$13, avatar_url=$14,
avatar_version=$15, background_media_asset_id=$16, background_url=$17,
caller_ringtone_id=$18, theme_mode_override=$19, font_size_preset_override=$20,
appearance_override_updated_at=$21, is_primary=$22, is_private=$23,
is_active=$24, isolation_level=$25, purpose_hint=$26, status=$27,
retired_at=$28, inherits_profile_from_owner=$29, overridden_profile_fields=$30,
last_profile_sync_at=$31, last_profile_sync_source=$32, last_activated_at=$33,
version=$34, created_at=$35, updated_at=$36
WHERE persona_id=$1 AND version=$37`,
			persona.PersonaID, persona.UserID, persona.DisplayName,
			persona.NicknameCustomized, persona.UserHandle, persona.Bio,
			persona.IdentityTags, persona.TaxonomyReleaseID, persona.Gender,
			persona.BirthDate, persona.Region, persona.RegionTagRef,
			persona.AvatarMediaAssetID, persona.AvatarURL, persona.AvatarVersion,
			persona.BackgroundMediaAssetID, persona.BackgroundURL,
			persona.CallerRingtoneID, persona.ThemeModeOverride,
			persona.FontSizePresetOverride, persona.AppearanceOverrideUpdatedAt,
			persona.IsPrimary, persona.IsPrivate, persona.IsActive,
			persona.IsolationLevel, persona.PurposeHint, persona.Status,
			persona.RetiredAt, persona.InheritsProfileFromOwner,
			persona.OverriddenProfileFields, persona.LastProfileSyncAt,
			persona.LastProfileSyncSource, persona.LastActivatedAt, nextVersion,
			persona.CreatedAt, persona.UpdatedAt, currentVersion,
		)
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if tag.RowsAffected() != 1 {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		return personaports.PersonaCommandResult{
				PersonaID: persona.PersonaID,
				Version:   nextVersion,
			}, s.appendPacket(ctx, tx, persona.UserID, persona.PersonaID, nextVersion,
				eventType, meta)
	})
}

func (s *PersonaCommandPostgresStore) CommitActivation(
	ctx context.Context,
	ownerID string,
	personaID string,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	ownerID = strings.TrimSpace(ownerID)
	personaID = strings.TrimSpace(personaID)
	if ownerID == "" || personaID == "" {
		return personaports.PersonaCommandResult{},
			errors.New("persona activation requires owner and persona identity")
	}
	return s.commit(ctx, meta, func(tx pgx.Tx) (personaports.PersonaCommandResult, error) {
		var currentVersion int64
		err := tx.QueryRow(ctx,
			`SELECT version FROM personas
			 WHERE user_id=$1 AND persona_id=$2
			   AND COALESCE(status, 'active') <> 'retired'
			 FOR UPDATE`,
			ownerID, personaID,
		).Scan(&currentVersion)
		if errors.Is(err, pgx.ErrNoRows) {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if _, err := tx.Exec(ctx,
			`UPDATE personas SET is_active = false, updated_at = NOW()
			 WHERE user_id = $1 AND is_active = true AND persona_id <> $2`,
			ownerID, personaID,
		); err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		nextVersion := currentVersion + 1
		tag, err := tx.Exec(ctx,
			`UPDATE personas
			 SET is_active = true, last_activated_at = NOW(), updated_at = NOW(), version = $3
			 WHERE user_id = $1 AND persona_id = $2 AND version = $4`,
			ownerID, personaID, nextVersion, currentVersion,
		)
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if tag.RowsAffected() != 1 {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		return personaports.PersonaCommandResult{
				PersonaID: personaID,
				Version:   nextVersion,
			}, s.appendPacket(ctx, tx, ownerID, personaID, nextVersion,
				personaports.PersonaActivatedEvent, meta)
	})
}

// commit 统一承载 replay 检查、事务边界与 receipt 冲突映射。
func (s *PersonaCommandPostgresStore) commit(
	ctx context.Context,
	meta personaports.PersonaCommandMeta,
	apply func(tx pgx.Tx) (personaports.PersonaCommandResult, error),
) (personaports.PersonaCommandResult, error) {
	if strings.TrimSpace(meta.IdempotencyKey) == "" ||
		strings.TrimSpace(meta.CommandDigest) == "" {
		return personaports.PersonaCommandResult{}, personaports.ErrPersonaCommandMetaRequired
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return personaports.PersonaCommandResult{}, err
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if result, replayed, err := s.replay(ctx, tx, meta); err != nil || replayed {
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if err := tx.Commit(ctx); err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		return result, nil
	}
	result, err := apply(tx)
	if err != nil {
		return personaports.PersonaCommandResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return personaports.PersonaCommandResult{}, err
	}
	return result, nil
}

func (s *PersonaCommandPostgresStore) replay(
	ctx context.Context,
	tx pgx.Tx,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, bool, error) {
	var (
		storedDigest string
		resultJSON   []byte
	)
	err := tx.QueryRow(ctx, `
SELECT command_digest, result_json
FROM personas_command_receipts
WHERE idempotency_key=$1`, meta.IdempotencyKey).Scan(&storedDigest, &resultJSON)
	if errors.Is(err, pgx.ErrNoRows) {
		return personaports.PersonaCommandResult{}, false, nil
	}
	if err != nil {
		return personaports.PersonaCommandResult{}, false, err
	}
	if storedDigest != meta.CommandDigest {
		return personaports.PersonaCommandResult{}, false,
			personaports.ErrPersonaIdempotencyConflict
	}
	var result personaports.PersonaCommandResult
	if err := json.Unmarshal(resultJSON, &result); err != nil {
		return personaports.PersonaCommandResult{}, false, err
	}
	result.Replayed = true
	return result, true, nil
}

func (s *PersonaCommandPostgresStore) appendPacket(
	ctx context.Context,
	tx pgx.Tx,
	ownerID string,
	personaID string,
	version int64,
	eventType string,
	meta personaports.PersonaCommandMeta,
) error {
	payload, err := json.Marshal(struct {
		UserID    string `json:"userId"`
		PersonaID string `json:"personaId"`
	}{UserID: ownerID, PersonaID: personaID})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,NOW())`,
		stablePersonaPacketID("event", meta.IdempotencyKey),
		personaID, version, eventType, payload,
	); err != nil {
		return err
	}
	resultJSON, err := json.Marshal(personaports.PersonaCommandResult{
		PersonaID: personaID,
		Version:   version,
	})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_command_receipts(
  receipt_id, aggregate_id, idempotency_key, command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)`,
		stablePersonaPacketID("receipt", meta.IdempotencyKey),
		personaID,
		meta.IdempotencyKey,
		meta.CommandDigest,
		version,
		resultJSON,
	); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return personaports.ErrPersonaIdempotencyConflict
		}
		return err
	}
	return nil
}
