package persistence

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
	usertelemetry "quwoquan_service/services/user-service/internal/domain/user/telemetry"
)

// PgPersonaStore extends pgPersonaStoreBase with domain-specific methods.
type PgPersonaStore struct {
	pgPersonaStoreBase
	mongoDB *mongo.Database
}

var _ repository.PersonaRepository = (*PgPersonaStore)(nil)

const personaNullableSafeCols = `user_id, display_name, COALESCE(user_handle, ''), COALESCE(phone, ''), COALESCE(email, ''), COALESCE(avatar_url, ''), COALESCE(caller_ringtone_id, ''), COALESCE(theme_mode_override, ''), COALESCE(font_size_preset_override, ''), appearance_override_updated_at, is_primary, is_private, is_active, COALESCE(status, 'active'), retired_at, COALESCE(sub_account_id, ''), COALESCE(isolation_level, ''), COALESCE(purpose_hint, ''), COALESCE(inherits_profile_from_owner, false), COALESCE(array_to_string(overridden_profile_fields, ','), ''), last_profile_sync_at, COALESCE(last_profile_sync_source, ''), last_activated_at, invite_count, created_at, updated_at`

func NewPgPersonaStore(pool *pgxpool.Pool) *PgPersonaStore {
	return &PgPersonaStore{pgPersonaStoreBase: pgPersonaStoreBase{pool: pool}}
}

func (s *PgPersonaStore) WithMongoDatabase(db *mongo.Database) *PgPersonaStore {
	s.mongoDB = db
	return s
}

func (s *PgPersonaStore) FindByID(ctx context.Context, id string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE sub_account_id = $1`, id))
}

// FindByUserID delegates to the generated ListByUserID (FK-based list).
func (s *PgPersonaStore) FindByUserID(ctx context.Context, userID string) ([]model.Persona, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_id = $1 ORDER BY created_at DESC`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []model.Persona
	for rows.Next() {
		var e model.Persona
		if err := rows.Scan(
			&e.UserID,
			&e.DisplayName,
			&e.UserHandle,
			&e.Phone,
			&e.Email,
			&e.AvatarURL,
			&e.CallerRingtoneID,
			&e.ThemeModeOverride,
			&e.FontSizePresetOverride,
			&e.AppearanceOverrideUpdatedAt,
			&e.IsPrimary,
			&e.IsPrivate,
			&e.IsActive,
			&e.Status,
			&e.RetiredAt,
			&e.SubAccountID,
			&e.IsolationLevel,
			&e.PurposeHint,
			&e.InheritsProfileFromOwner,
			&e.OverriddenProfileFields,
			&e.LastProfileSyncAt,
			&e.LastProfileSyncSource,
			&e.LastActivatedAt,
			&e.InviteCount,
			&e.CreatedAt,
			&e.UpdatedAt,
		); err != nil {
			return nil, err
		}
		result = append(result, e)
	}
	return result, rows.Err()
}

// Update delegates to the generated full-column update.
func (s *PgPersonaStore) Update(ctx context.Context, p *model.Persona) error {
	return s.pgPersonaStoreBase.Update(ctx, p)
}

func (s *PgPersonaStore) FindActiveByUserID(ctx context.Context, userID string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_id = $1 AND is_active = true AND COALESCE(status, 'active') <> 'retired'`, userID))
}

func (s *PgPersonaStore) FindByUserHandle(ctx context.Context, userHandle string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE user_handle = $1`, userHandle))
}

func (s *PgPersonaStore) DeactivateAll(ctx context.Context, userID string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE personas SET is_active = false, updated_at = NOW() WHERE user_id = $1 AND is_active = true`, userID)
	return err
}

func (s *PgPersonaStore) ActivateOne(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE personas SET is_active = true, updated_at = NOW() WHERE sub_account_id = $1 AND COALESCE(status, 'active') <> 'retired'`, id)
	return err
}

// FindBySubAccountID looks up a persona by its public sub_account_id.
func (s *PgPersonaStore) FindBySubAccountID(ctx context.Context, subAccountID string) (*model.Persona, error) {
	return scanPersona(s.pool.QueryRow(ctx,
		`SELECT `+personaNullableSafeCols+` FROM personas WHERE sub_account_id = $1`, subAccountID))
}

func (s *PgPersonaStore) HasAttributedHistory(ctx context.Context, subAccountID string) (bool, error) {
	var hasPGHistory bool
	err := s.pool.QueryRow(ctx, `
		SELECT
			EXISTS(
				SELECT 1
				FROM invite_records
				WHERE inviter_sub_account_id = $1
				LIMIT 1
			)
			OR EXISTS(
				SELECT 1
				FROM greeting_requests
				WHERE requester_sub_account_id = $1
				LIMIT 1
			)
			OR EXISTS(
				SELECT 1
				FROM greeting_requests
				WHERE target_sub_account_id = $1
				LIMIT 1
			)
	`, subAccountID).Scan(&hasPGHistory)
	if err != nil {
		return false, err
	}
	if hasPGHistory {
		return true, nil
	}
	if s.mongoDB == nil {
		return false, nil
	}
	hasMongoHistory, err := s.hasMongoAttributedHistory(ctx, subAccountID)
	if err != nil {
		return false, err
	}
	if hasMongoHistory {
		usertelemetry.Collector().RecordRetiredAttributionFallback()
		usertelemetry.RolloutCollector().RecordAttributionMismatch()
	}
	return hasMongoHistory, nil
}

func (s *PgPersonaStore) hasMongoAttributedHistory(ctx context.Context, subAccountID string) (bool, error) {
	checks := []struct {
		collection string
		filter     bson.M
	}{
		{
			collection: "posts",
			filter: bson.M{
				"authorId": subAccountID,
			},
		},
		{
			collection: "comments",
			filter: bson.M{
				"authorId": subAccountID,
			},
		},
		{
			collection: "messages",
			filter: bson.M{
				"senderSubAccountId": subAccountID,
			},
		},
		{
			collection: "notifications",
			filter: bson.M{
				"senderUserId": subAccountID,
			},
		},
	}
	for _, check := range checks {
		count, err := s.mongoDB.Collection(check.collection).CountDocuments(ctx, check.filter)
		if err != nil {
			return false, err
		}
		if count > 0 {
			return true, nil
		}
	}
	return false, nil
}
