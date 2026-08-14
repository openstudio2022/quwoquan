package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

const userProfileSearchBackfillEventType = "UserProfileSearchBackfillRequested"

// PgProfileStore extends the object-local generated base with domain queries.
type PgProfileStore struct {
	pool *pgxpool.Pool
}

var _ repository.UserProfileStore = (*PgProfileStore)(nil)

func NewPgProfileStore(pool *pgxpool.Pool) *PgProfileStore {
	return &PgProfileStore{pool: pool}
}

const userProfileNullableSafeCols = `user_id, COALESCE(account_state, 'active'), COALESCE(identity_origin, ''), logical_shard, COALESCE(anonymous_retention_policy, ''), COALESCE(phone, ''), COALESCE(nickname, ''), COALESCE(nickname_customized, false), COALESCE(avatar_url, ''), COALESCE(avatar_asset_id, ''), avatar_version, COALESCE(background_url, ''), COALESCE(background_asset_id, ''), COALESCE(bio, ''), COALESCE(identity_tags, ''), COALESCE(gender, ''), birth_date::text, COALESCE(region, ''), COALESCE(region_code, ''), profile_version, follower_count, following_count, post_count, circle_count, like_count, COALESCE(owner_display_name, ''), persona_count, created_at, updated_at`

type userProfileScanner interface {
	Scan(dest ...any) error
}

func scanNullableSafeUserProfile(scanner userProfileScanner) (*model.UserProfile, error) {
	e := &model.UserProfile{}
	err := scanner.Scan(
		&e.UserID,
		&e.AccountState,
		&e.IdentityOrigin,
		&e.LogicalShard,
		&e.AnonymousRetentionPolicy,
		&e.Phone,
		&e.Nickname,
		&e.NicknameCustomized,
		&e.AvatarURL,
		&e.AvatarAssetID,
		&e.AvatarVersion,
		&e.BackgroundURL,
		&e.BackgroundAssetID,
		&e.Bio,
		&e.IdentityTags,
		&e.Gender,
		&e.BirthDate,
		&e.Region,
		&e.RegionCode,
		&e.ProfileVersion,
		&e.FollowerCount,
		&e.FollowingCount,
		&e.PostCount,
		&e.CircleCount,
		&e.LikeCount,
		&e.OwnerDisplayName,
		&e.PersonaCount,
		&e.CreatedAt,
		&e.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return e, nil
}

// FindByID overrides generated lookup so newly nullable profile fields
// (e.g. background_url) never break read paths during transitional data states.
func (s *PgProfileStore) FindByID(ctx context.Context, id string) (*model.UserProfile, error) {
	return scanNullableSafeUserProfile(
		s.pool.QueryRow(ctx, `SELECT `+userProfileNullableSafeCols+` FROM user_profiles WHERE user_id = $1`, id),
	)
}

// CreateAccount creates only authoritative UserAccount state. Public profile
// columns start as an empty projection and are populated exclusively by the
// durable PersonaProfileProjector after Persona creation.
func (s *PgProfileStore) CreateAccount(
	ctx context.Context,
	command repository.UserAccountCreate,
) error {
	if strings.TrimSpace(command.UserID) == "" {
		return errors.New("invalid UserAccount creation state")
	}
	if command.PersonaCount <= 0 {
		command.PersonaCount = 1
	}
	now := time.Now().UTC()

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin UserAccount creation transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if err := insertUserAccountRow(ctx, tx, command, now); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit UserAccount creation: %w", err)
	}
	return nil
}

func insertUserAccountRow(
	ctx context.Context,
	tx pgx.Tx,
	command repository.UserAccountCreate,
	now time.Time,
) error {
	_, err := tx.Exec(ctx, `
		INSERT INTO user_profiles (
			user_id, account_state, auth_epoch, identity_origin, logical_shard,
			anonymous_retention_policy, phone, nickname, nickname_customized,
			avatar_version, profile_version, persona_count, created_at, updated_at
		) VALUES (
			$1, $2, 1, $3, $4, $5, NULLIF($6, ''), '', false, 0, 0, $7, $8, $8
		)`,
		strings.TrimSpace(command.UserID),
		strings.TrimSpace(command.AccountState),
		strings.TrimSpace(command.IdentityOrigin),
		command.LogicalShard,
		strings.TrimSpace(command.AnonymousRetentionPolicy),
		strings.TrimSpace(command.Phone),
		command.PersonaCount,
		now,
	)
	if err != nil {
		return fmt.Errorf("insert UserAccount: %w", err)
	}
	return nil
}

func (s *PgProfileStore) PromoteRegistration(
	ctx context.Context,
	command repository.RegistrationPromotion,
) error {
	userID := strings.TrimSpace(command.UserID)
	if userID == "" {
		return errors.New("registration promotion requires UserAccount identity")
	}
	phone := strings.TrimSpace(command.Phone)
	tag, err := s.pool.Exec(ctx, `
		UPDATE user_profiles
			SET account_state=CASE WHEN account_state='anonymous' THEN 'active' ELSE account_state END,
			    anonymous_retention_policy=CASE WHEN account_state='anonymous' THEN 'preserve' ELSE anonymous_retention_policy END,
			    phone=CASE WHEN NULLIF(BTRIM(COALESCE(phone, '')), '') IS NULL AND $2 <> '' THEN $2 ELSE phone END,
			    updated_at=NOW()
			WHERE user_id=$1`,
		userID,
		phone,
	)
	if err != nil {
		return fmt.Errorf("promote UserAccount registration: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("UserAccount not found: %s", userID)
	}
	return nil
}

func appendUserProfileTagProjection(
	ctx context.Context,
	tx pgx.Tx,
	projection repository.UserProfileTagProjection,
) error {
	payload, err := json.Marshal(struct {
		UserID            string    `json:"userId"`
		TagRefs           []string  `json:"tagRefs"`
		TaxonomyReleaseID string    `json:"taxonomyReleaseId"`
		ProfileVersion    int64     `json:"profileVersion"`
		OccurredAt        time.Time `json:"occurredAt"`
	}{
		UserID:            projection.UserID,
		TagRefs:           projection.TagRefs,
		TaxonomyReleaseID: projection.TaxonomyReleaseID,
		ProfileVersion:    projection.ProfileVersion,
		OccurredAt:        projection.OccurredAt.UTC(),
	})
	if err != nil {
		return fmt.Errorf("marshal user profile tag projection: %w", err)
	}
	if _, err := tx.Exec(
		ctx,
		`INSERT INTO user_account_outbox (
			event_id, aggregate_id, aggregate_version, event_type,
			payload_json, occurred_at, next_attempt_at
		) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $6)`,
		projection.EventID,
		projection.UserID,
		projection.ProfileVersion,
		userevent.UserProfileTagsChanged,
		string(payload),
		projection.OccurredAt.UTC(),
	); err != nil {
		return fmt.Errorf("enqueue user profile tag projection: %w", err)
	}
	return nil
}

// EnqueueUserProfileSearchBackfill re-enqueues one profile's public snapshot
// into the search projection outbox (cold-start / index-rebuild reconcile for
// user.profile documents). It reuses the exact write-path projection shape and
// outbox relay, so Search consumes the same single-track
// UserProfileSearchProjectionRequested event either way and User never writes
// the search provider directly.
func (s *PgProfileStore) EnqueueUserProfileSearchBackfill(
	ctx context.Context,
	profile model.UserProfile,
	occurredAt time.Time,
) error {
	if strings.TrimSpace(profile.UserID) == "" || int64(profile.ProfileVersion) <= 0 {
		return errors.New("user profile search backfill requires a versioned profile")
	}
	operation := "upsert"
	if !strings.EqualFold(strings.TrimSpace(profile.AccountState), "active") {
		// Non-active accounts must not resurface via backfill; lifecycle events
		// own suspension/closure, the reconcile only guarantees absence.
		operation = "delete"
	}
	projection := repository.UserProfileSearchProjection{
		EventID: userProfileSearchBackfillEventID(
			profile.UserID,
			int64(profile.ProfileVersion),
			occurredAt,
		),
		UserID:         profile.UserID,
		ProfileVersion: int64(profile.ProfileVersion),
		EventType:      userProfileSearchBackfillEventType,
		OccurredAt:     occurredAt,
		Payload: repository.UserProfileSearchProjectionPayload{
			Operation:     operation,
			Nickname:      profile.Nickname,
			AvatarURL:     profile.AvatarURL,
			Bio:           profile.Bio,
			IdentityTags:  parsePgTextArray(profile.IdentityTags),
			FollowerCount: profile.FollowerCount,
			PostCount:     profile.PostCount,
			UpdatedAt:     profile.UpdatedAt,
		},
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin user profile search backfill: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := appendUserProfileSearchProjections(ctx, tx, []repository.UserProfileSearchProjection{projection}); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// parsePgTextArray decodes the profile identity_tags column, which is stored
// as the text form of a PostgreSQL text[] literal ({tag1,tag2}).
func parsePgTextArray(raw string) []string {
	raw = strings.TrimSpace(raw)
	raw = strings.TrimPrefix(raw, "{")
	raw = strings.TrimSuffix(raw, "}")
	if raw == "" {
		return []string{}
	}
	parts := strings.Split(raw, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.Trim(strings.TrimSpace(part), `"`)
		if part != "" {
			out = append(out, part)
		}
	}
	return out
}

func appendUserProfileSearchProjections(
	ctx context.Context,
	tx pgx.Tx,
	projections []repository.UserProfileSearchProjection,
) error {
	for _, projection := range projections {
		if strings.TrimSpace(projection.UserID) == "" ||
			projection.ProfileVersion <= 0 ||
			projection.OccurredAt.IsZero() ||
			!isUserProfileSearchProjectionEvent(projection.EventType) {
			return errors.New("invalid user profile search projection")
		}
		eventID := strings.TrimSpace(projection.EventID)
		if eventID == "" {
			eventID = userProfileSearchProjectionEventID(
				projection.UserID,
				projection.ProfileVersion,
				projection.EventType,
			)
		}
		payload := projection.Payload
		payload.EventID = eventID
		payload.UserID = strings.TrimSpace(projection.UserID)
		payload.ProfileVersion = projection.ProfileVersion
		payload.UpdatedAt = payload.UpdatedAt.UTC()
		if payload.UpdatedAt.IsZero() ||
			(payload.Operation != "upsert" && payload.Operation != "delete") {
			return errors.New("invalid user profile search projection payload")
		}
		if payload.IdentityTags == nil {
			payload.IdentityTags = []string{}
		}
		payloadJSON, err := json.Marshal(payload)
		if err != nil {
			return fmt.Errorf("encode user profile search projection: %w", err)
		}
		if _, err := tx.Exec(
			ctx,
			`INSERT INTO user_profile_search_outbox (
				event_id, user_id, profile_version, event_type, payload_json, occurred_at,
				next_attempt_at
			) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $6)
			ON CONFLICT DO NOTHING`,
			eventID,
			projection.UserID,
			projection.ProfileVersion,
			projection.EventType,
			string(payloadJSON),
			projection.OccurredAt.UTC(),
		); err != nil {
			return fmt.Errorf("enqueue user profile search projection: %w", err)
		}
	}
	return nil
}

func userProfileSearchProjectionEventID(
	userID string,
	profileVersion int64,
	eventType string,
) string {
	digest := sha256.Sum256([]byte(fmt.Sprintf(
		"user-profile-search-projection\x00%s\x00%d\x00%s",
		strings.TrimSpace(userID),
		profileVersion,
		eventType,
	)))
	return "ups_" + hex.EncodeToString(digest[:24])
}

func userProfileSearchBackfillEventID(
	userID string,
	profileVersion int64,
	occurredAt time.Time,
) string {
	digest := sha256.Sum256([]byte(fmt.Sprintf(
		"user-profile-search-backfill\x00%s\x00%d\x00%d",
		strings.TrimSpace(userID),
		profileVersion,
		occurredAt.UTC().UnixNano(),
	)))
	return "ups_" + hex.EncodeToString(digest[:24])
}

func isUserProfileSearchProjectionEvent(eventType string) bool {
	switch eventType {
	case userevent.UserProfileUpdated,
		userevent.UserAvatarUpdated,
		userevent.UserAccountClosed,
		userProfileSearchBackfillEventType:
		return true
	default:
		return false
	}
}

func (s *PgProfileStore) FindByNickname(ctx context.Context, nickname string) (*model.UserProfile, error) {
	row := s.pool.QueryRow(ctx,
		`SELECT `+userProfileNullableSafeCols+` FROM user_profiles WHERE nickname = $1`, nickname)
	return scanNullableSafeUserProfile(row)
}

func (s *PgProfileStore) SearchProfiles(ctx context.Context, query string, limit int) ([]model.UserProfile, error) {
	normalized := strings.TrimSpace(query)
	if normalized == "" {
		return []model.UserProfile{}, nil
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > 50 {
		limit = 50
	}
	pattern := "%" + normalized + "%"
	rows, err := s.pool.Query(
		ctx,
		`SELECT `+userProfileNullableSafeCols+`
		FROM user_profiles
		WHERE user_id ILIKE $1
		   OR nickname ILIKE $1
		   OR owner_display_name ILIKE $1
		   OR bio ILIKE $1
		   OR region ILIKE $1
		ORDER BY follower_count DESC, updated_at DESC
		LIMIT $2`,
		pattern,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	results := make([]model.UserProfile, 0, limit)
	for rows.Next() {
		profile, err := scanNullableSafeUserProfile(rows)
		if err != nil {
			return nil, err
		}
		results = append(results, *profile)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return results, nil
}

// ListProfilesForIndex enumerates profiles in stable user_id order for cold-start
// search backfill via keyset pagination (user_id > afterUserID). It scans every
// column in userProfileCols (including identity_tags) so the search projection
// sees the full profile; eligibility filtering is applied by the backfill caller
// so the reader stays a plain enumeration.
func (s *PgProfileStore) ListProfilesForIndex(ctx context.Context, afterUserID string, limit int) ([]model.UserProfile, error) {
	if limit <= 0 {
		limit = 500
	}
	rows, err := s.pool.Query(
		ctx,
		`SELECT `+userProfileNullableSafeCols+`
		FROM user_profiles
		WHERE user_id > $1
		ORDER BY user_id ASC
		LIMIT $2`,
		afterUserID,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	results := make([]model.UserProfile, 0, limit)
	for rows.Next() {
		e, err := scanNullableSafeUserProfile(rows)
		if err != nil {
			return nil, err
		}
		results = append(results, *e)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return results, nil
}
