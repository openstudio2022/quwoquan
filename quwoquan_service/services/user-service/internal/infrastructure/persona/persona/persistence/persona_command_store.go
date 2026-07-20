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

	personaports "quwoquan_service/services/user-service/internal/domain/persona/persona/ports"
	usermodel "quwoquan_service/services/user-service/internal/domain/user/model"
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
	if persona == nil || strings.TrimSpace(persona.SubAccountID) == "" {
		return personaports.PersonaCommandResult{},
			errors.New("persona create requires aggregate identity")
	}
	return s.commit(ctx, meta, func(tx pgx.Tx) (personaports.PersonaCommandResult, error) {
		now := time.Now().UTC()
		persona.CreatedAt = now
		persona.UpdatedAt = now
		if _, err := tx.Exec(ctx,
			`INSERT INTO personas (user_id, display_name, user_handle, phone, email, avatar_url, avatar_version, background_url, caller_ringtone_id, theme_mode_override, font_size_preset_override, appearance_override_updated_at, is_primary, is_private, is_active, status, retired_at, sub_account_id, isolation_level, purpose_hint, inherits_profile_from_owner, overridden_profile_fields, last_profile_sync_at, last_profile_sync_source, last_activated_at, created_at, updated_at, version) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, 1)`,
			persona.UserID, persona.DisplayName, persona.UserHandle, persona.Phone,
			persona.Email, persona.AvatarURL, persona.AvatarVersion, persona.BackgroundURL,
			persona.CallerRingtoneID, persona.ThemeModeOverride, persona.FontSizePresetOverride,
			persona.AppearanceOverrideUpdatedAt, persona.IsPrimary, persona.IsPrivate,
			persona.IsActive, persona.Status, persona.RetiredAt, persona.SubAccountID,
			persona.IsolationLevel, persona.PurposeHint, persona.InheritsProfileFromOwner,
			persona.OverriddenProfileFields, persona.LastProfileSyncAt,
			persona.LastProfileSyncSource, persona.LastActivatedAt,
			persona.CreatedAt, persona.UpdatedAt,
		); err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		return personaports.PersonaCommandResult{
				SubAccountID: persona.SubAccountID,
				Version:      1,
			}, s.appendPacket(ctx, tx, persona.UserID, persona.SubAccountID, 1,
				personaports.PersonaCreatedEvent, meta)
	})
}

func (s *PersonaCommandPostgresStore) CommitMutation(
	ctx context.Context,
	persona *usermodel.Persona,
	eventType string,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	if persona == nil || strings.TrimSpace(persona.SubAccountID) == "" {
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
			`SELECT version FROM personas WHERE sub_account_id=$1 FOR UPDATE`,
			persona.SubAccountID,
		).Scan(&currentVersion)
		if errors.Is(err, pgx.ErrNoRows) {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		nextVersion := currentVersion + 1
		persona.UpdatedAt = time.Now().UTC()
		tag, err := tx.Exec(ctx,
			`UPDATE personas SET user_id=$2, display_name=$3, user_handle=$4, phone=$5, email=$6, avatar_url=$7, avatar_version=$8, background_url=$9, caller_ringtone_id=$10, theme_mode_override=$11, font_size_preset_override=$12, appearance_override_updated_at=$13, is_primary=$14, is_private=$15, is_active=$16, status=$17, retired_at=$18, isolation_level=$19, purpose_hint=$20, inherits_profile_from_owner=$21, overridden_profile_fields=$22, last_profile_sync_at=$23, last_profile_sync_source=$24, last_activated_at=$25, updated_at=$26, version=$27 WHERE sub_account_id = $1 AND version = $28`,
			persona.SubAccountID, persona.UserID, persona.DisplayName, persona.UserHandle,
			persona.Phone, persona.Email, persona.AvatarURL, persona.AvatarVersion,
			persona.BackgroundURL, persona.CallerRingtoneID, persona.ThemeModeOverride,
			persona.FontSizePresetOverride, persona.AppearanceOverrideUpdatedAt,
			persona.IsPrimary, persona.IsPrivate, persona.IsActive, persona.Status,
			persona.RetiredAt, persona.IsolationLevel, persona.PurposeHint,
			persona.InheritsProfileFromOwner, persona.OverriddenProfileFields,
			persona.LastProfileSyncAt, persona.LastProfileSyncSource, persona.LastActivatedAt,
			persona.UpdatedAt, nextVersion, currentVersion,
		)
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if tag.RowsAffected() != 1 {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		return personaports.PersonaCommandResult{
				SubAccountID: persona.SubAccountID,
				Version:      nextVersion,
			}, s.appendPacket(ctx, tx, persona.UserID, persona.SubAccountID, nextVersion,
				eventType, meta)
	})
}

func (s *PersonaCommandPostgresStore) CommitActivation(
	ctx context.Context,
	ownerID string,
	subAccountID string,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	ownerID = strings.TrimSpace(ownerID)
	subAccountID = strings.TrimSpace(subAccountID)
	if ownerID == "" || subAccountID == "" {
		return personaports.PersonaCommandResult{},
			errors.New("persona activation requires owner and sub-account identity")
	}
	return s.commit(ctx, meta, func(tx pgx.Tx) (personaports.PersonaCommandResult, error) {
		var currentVersion int64
		err := tx.QueryRow(ctx,
			`SELECT version FROM personas
			 WHERE user_id=$1 AND sub_account_id=$2
			   AND COALESCE(status, 'active') <> 'retired'
			 FOR UPDATE`,
			ownerID, subAccountID,
		).Scan(&currentVersion)
		if errors.Is(err, pgx.ErrNoRows) {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if _, err := tx.Exec(ctx,
			`UPDATE personas SET is_active = false, updated_at = NOW()
			 WHERE user_id = $1 AND is_active = true AND sub_account_id <> $2`,
			ownerID, subAccountID,
		); err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		nextVersion := currentVersion + 1
		tag, err := tx.Exec(ctx,
			`UPDATE personas
			 SET is_active = true, last_activated_at = NOW(), updated_at = NOW(), version = $3
			 WHERE user_id = $1 AND sub_account_id = $2 AND version = $4`,
			ownerID, subAccountID, nextVersion, currentVersion,
		)
		if err != nil {
			return personaports.PersonaCommandResult{}, err
		}
		if tag.RowsAffected() != 1 {
			return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
		}
		return personaports.PersonaCommandResult{
				SubAccountID: subAccountID,
				Version:      nextVersion,
			}, s.appendPacket(ctx, tx, ownerID, subAccountID, nextVersion,
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
	subAccountID string,
	version int64,
	eventType string,
	meta personaports.PersonaCommandMeta,
) error {
	payload, err := json.Marshal(struct {
		UserID       string `json:"userId"`
		SubAccountID string `json:"subAccountId"`
	}{UserID: ownerID, SubAccountID: subAccountID})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,NOW())`,
		stablePersonaPacketID("event", meta.IdempotencyKey),
		subAccountID, version, eventType, payload,
	); err != nil {
		return err
	}
	resultJSON, err := json.Marshal(personaports.PersonaCommandResult{
		SubAccountID: subAccountID,
		Version:      version,
	})
	if err != nil {
		return err
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO personas_command_receipts(
  receipt_id, aggregate_id, idempotency_key, command_digest, aggregate_version, result_json
) VALUES ($1,$2,$3,$4,$5,$6)`,
		stablePersonaPacketID("receipt", meta.IdempotencyKey),
		subAccountID,
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
