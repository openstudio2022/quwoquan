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
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	generated "quwoquan_service/services/user-service/generated/account/user_account/persistence/user/persistence"
	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

// PgProfileStore extends the object-local generated base with domain queries.
type PgProfileStore struct {
	*generated.PGUserAccountStoreBase
	pool *pgxpool.Pool
}

var _ repository.UserProfileStore = (*PgProfileStore)(nil)
var _ repository.UserProfileCommandStore = (*PgProfileStore)(nil)

func NewPgProfileStore(pool *pgxpool.Pool) *PgProfileStore {
	return &PgProfileStore{
		PGUserAccountStoreBase: generated.NewPGUserAccountStoreBase(pool),
		pool:                   pool,
	}
}

const userProfileNullableSafeCols = `user_id, COALESCE(account_state, 'active'), COALESCE(identity_origin, ''), logical_shard, COALESCE(anonymous_retention_policy, ''), COALESCE(phone, ''), COALESCE(nickname, ''), COALESCE(nickname_customized, false), COALESCE(avatar_url, ''), COALESCE(avatar_asset_id, ''), avatar_version, COALESCE(background_url, ''), COALESCE(background_asset_id, ''), COALESCE(bio, ''), COALESCE(identity_tags, ''), COALESCE(gender, ''), birth_date::text, COALESCE(region, ''), COALESCE(region_code, ''), COALESCE(status, 'active'), profile_version, follower_count, following_count, post_count, circle_count, like_count, COALESCE(owner_display_name, ''), sub_account_count, created_at, updated_at`

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
		&e.Status,
		&e.ProfileVersion,
		&e.FollowerCount,
		&e.FollowingCount,
		&e.PostCount,
		&e.CircleCount,
		&e.LikeCount,
		&e.OwnerDisplayName,
		&e.SubAccountCount,
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

// Create overrides the generated Create to apply business defaults.
func (s *PgProfileStore) Create(ctx context.Context, p *model.UserProfile) error {
	if p == nil || strings.TrimSpace(p.UserID) == "" {
		return errors.New("invalid UserProfile creation state")
	}
	if p.AuthEpoch == 0 {
		p.AuthEpoch = 1
	}
	if p.Status == "" {
		p.Status = "active"
	}
	if p.ProfileVersion == 0 {
		p.ProfileVersion = 1
	}
	if p.AvatarURL != "" && p.AvatarAssetID == "" {
		p.AvatarAssetID = "ua_" + p.UserID
	}
	if p.AvatarURL != "" && p.AvatarVersion == 0 {
		p.AvatarVersion = 1
	}
	now := time.Now().UTC()
	p.CreatedAt = now
	p.UpdatedAt = now

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("begin UserProfile creation transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	if err := insertUserProfileRow(ctx, tx, p); err != nil {
		return err
	}
	if err := appendUserProfileSearchProjections(
		ctx,
		tx,
		[]repository.UserProfileSearchProjection{{
			UserID:         p.UserID,
			ProfileVersion: int64(p.ProfileVersion),
			EventType:      userevent.UserRegistered,
			OccurredAt:     p.CreatedAt,
		}},
	); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit UserProfile creation: %w", err)
	}
	return nil
}

func insertUserProfileRow(
	ctx context.Context,
	execer profileExecer,
	p *model.UserProfile,
) error {
	_, err := execer.Exec(ctx, `
		INSERT INTO user_profiles (
			user_id, account_state, auth_epoch, suspension_case_ref, suspended_at,
			identity_origin, logical_shard, anonymous_retention_policy, phone,
			nickname, nickname_customized, avatar_url, avatar_asset_id,
			avatar_version, background_url, background_asset_id, bio, identity_tags,
			gender, birth_date, region, region_code, status, profile_version,
			follower_count, following_count, post_count, circle_count, like_count,
			owner_display_name, sub_account_count, created_at, updated_at
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
			$16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
			$29, $30, $31, $32, $33
		)`,
		p.UserID, p.AccountState, p.AuthEpoch, p.SuspensionCaseRef, p.SuspendedAt,
		p.IdentityOrigin, p.LogicalShard, p.AnonymousRetentionPolicy, p.Phone,
		p.Nickname, p.NicknameCustomized, p.AvatarURL, p.AvatarAssetID,
		p.AvatarVersion, p.BackgroundURL, p.BackgroundAssetID, p.Bio, p.IdentityTags,
		p.Gender, p.BirthDate, p.Region, p.RegionCode, p.Status, p.ProfileVersion,
		p.FollowerCount, p.FollowingCount, p.PostCount, p.CircleCount, p.LikeCount,
		p.OwnerDisplayName, p.SubAccountCount, p.CreatedAt, p.UpdatedAt,
	)
	if err != nil {
		return fmt.Errorf("insert UserProfile: %w", err)
	}
	return nil
}

// Update performs a selective update on editable profile fields and bumps version.
func (s *PgProfileStore) Update(ctx context.Context, p *model.UserProfile) error {
	p.UpdatedAt = time.Now().UTC()
	return updateProfileRow(ctx, s.pool, p)
}

type profileExecer interface {
	Exec(
		ctx context.Context,
		sql string,
		arguments ...any,
	) (pgconn.CommandTag, error)
}

func updateProfileRow(
	ctx context.Context,
	execer profileExecer,
	p *model.UserProfile,
) error {
	return updateProfileRowWithExpectedVersion(ctx, execer, p, nil)
}

func updateProfileRowVersioned(
	ctx context.Context,
	execer profileExecer,
	p *model.UserProfile,
	expectedVersion int64,
) error {
	return updateProfileRowWithExpectedVersion(
		ctx,
		execer,
		p,
		&expectedVersion,
	)
}

func updateProfileRowWithExpectedVersion(
	ctx context.Context,
	execer profileExecer,
	p *model.UserProfile,
	expectedVersion *int64,
) error {
	if p.UpdatedAt.IsZero() {
		p.UpdatedAt = time.Now().UTC()
	}
	query := `
		UPDATE user_profiles
			SET nickname=$2, nickname_customized=$3, avatar_url=$4, avatar_asset_id=$5, avatar_version=$6,
			    background_url=$7, background_asset_id=$8, bio=$9, gender=$10, birth_date=$11,
			    region=$12, region_code=$13, profile_version=$14, updated_at=$15,
			    identity_tags=$16
			WHERE user_id=$1`
	arguments := []any{
		p.UserID, p.Nickname, p.NicknameCustomized, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion,
		p.BackgroundURL, p.BackgroundAssetID, p.Bio, p.Gender, p.BirthDate, p.Region, p.RegionCode,
		p.ProfileVersion, p.UpdatedAt, p.IdentityTags,
	}
	if expectedVersion != nil {
		query += ` AND profile_version=$17`
		arguments = append(arguments, *expectedVersion)
	}
	tag, err := execer.Exec(ctx, query, arguments...)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		if expectedVersion != nil {
			return repository.ErrUserProfileVersionConflict
		}
		return fmt.Errorf("profile not found: %s", p.UserID)
	}
	return nil
}

type profileCommandQueryer interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func (s *PgProfileStore) ReplayUserProfileCommand(
	ctx context.Context,
	meta repository.UserProfileCommandMeta,
) (repository.UserProfileCommandResult, bool, error) {
	if err := validateUserProfileCommandMeta(meta); err != nil {
		return repository.UserProfileCommandResult{}, false, err
	}
	return replayUserProfileCommand(ctx, s.pool, meta)
}

func (s *PgProfileStore) CommitUserProfileCommand(
	ctx context.Context,
	profile *model.UserProfile,
	projection *repository.UserProfileTagProjection,
	searchProjections []repository.UserProfileSearchProjection,
	meta repository.UserProfileCommandMeta,
) (repository.UserProfileCommandResult, error) {
	if profile == nil || strings.TrimSpace(profile.UserID) == "" ||
		profile.ProfileVersion <= 0 {
		return repository.UserProfileCommandResult{},
			errors.New("invalid user profile command state")
	}
	if err := validateUserProfileCommandMeta(meta); err != nil {
		return repository.UserProfileCommandResult{}, err
	}
	if projection != nil && (strings.TrimSpace(projection.EventID) == "" ||
		strings.TrimSpace(projection.UserID) == "" ||
		strings.TrimSpace(projection.TaxonomyReleaseID) == "" ||
		projection.ProfileVersion <= 0 ||
		projection.OccurredAt.IsZero()) {
		return repository.UserProfileCommandResult{},
			errors.New("invalid user profile tag projection")
	}
	if len(searchProjections) == 0 {
		return repository.UserProfileCommandResult{},
			errors.New("user profile search projection is required")
	}
	for _, searchProjection := range searchProjections {
		if strings.TrimSpace(searchProjection.UserID) != profile.UserID ||
			searchProjection.ProfileVersion != int64(profile.ProfileVersion) ||
			searchProjection.OccurredAt.IsZero() ||
			!isUserProfileSearchProjectionEvent(searchProjection.EventType) {
			return repository.UserProfileCommandResult{},
				errors.New("invalid user profile search projection")
		}
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return repository.UserProfileCommandResult{},
			fmt.Errorf("begin user profile command transaction: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(
		ctx,
		`SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`,
		meta.IdempotencyKey,
	); err != nil {
		return repository.UserProfileCommandResult{},
			fmt.Errorf("lock user profile command key: %w", err)
	}
	if result, replayed, err := replayUserProfileCommand(
		ctx,
		tx,
		meta,
	); err != nil || replayed {
		if err != nil {
			return repository.UserProfileCommandResult{}, err
		}
		if err := tx.Commit(ctx); err != nil {
			return repository.UserProfileCommandResult{}, err
		}
		return result, nil
	}
	if err := updateProfileRowVersioned(
		ctx,
		tx,
		profile,
		int64(profile.ProfileVersion-1),
	); err != nil {
		return repository.UserProfileCommandResult{}, err
	}
	if err := appendUserProfileSearchProjections(
		ctx,
		tx,
		searchProjections,
	); err != nil {
		return repository.UserProfileCommandResult{}, err
	}
	if projection != nil {
		if err := appendUserProfileTagProjection(ctx, tx, *projection); err != nil {
			return repository.UserProfileCommandResult{}, err
		}
	}
	result := repository.UserProfileCommandResult{
		ProfileVersion: int64(profile.ProfileVersion),
	}
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return repository.UserProfileCommandResult{}, err
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO personas_command_receipts(
			receipt_id, aggregate_id, idempotency_key, command_digest,
			aggregate_version, result_json
		) VALUES ($1,$2,$3,$4,$5,$6)`,
		userProfileCommandReceiptID(meta.IdempotencyKey),
		profile.UserID,
		meta.IdempotencyKey,
		meta.CommandDigest,
		result.ProfileVersion,
		resultJSON,
	); err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return repository.UserProfileCommandResult{},
				repository.ErrUserProfileIdempotencyConflict
		}
		return repository.UserProfileCommandResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return repository.UserProfileCommandResult{},
			fmt.Errorf("commit user profile command: %w", err)
	}
	return result, nil
}

func validateUserProfileCommandMeta(
	meta repository.UserProfileCommandMeta,
) error {
	if strings.TrimSpace(meta.IdempotencyKey) == "" ||
		strings.TrimSpace(meta.CommandDigest) == "" {
		return repository.ErrUserProfileCommandMetaRequired
	}
	return nil
}

func replayUserProfileCommand(
	ctx context.Context,
	queryer profileCommandQueryer,
	meta repository.UserProfileCommandMeta,
) (repository.UserProfileCommandResult, bool, error) {
	var (
		storedDigest string
		resultJSON   []byte
	)
	err := queryer.QueryRow(ctx, `
		SELECT command_digest, result_json
		FROM personas_command_receipts
		WHERE idempotency_key=$1`,
		meta.IdempotencyKey,
	).Scan(&storedDigest, &resultJSON)
	if errors.Is(err, pgx.ErrNoRows) {
		return repository.UserProfileCommandResult{}, false, nil
	}
	if err != nil {
		return repository.UserProfileCommandResult{}, false, err
	}
	if storedDigest != meta.CommandDigest {
		return repository.UserProfileCommandResult{}, false,
			repository.ErrUserProfileIdempotencyConflict
	}
	var result repository.UserProfileCommandResult
	if err := json.Unmarshal(resultJSON, &result); err != nil {
		return repository.UserProfileCommandResult{}, false, err
	}
	result.Replayed = true
	return result, true, nil
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
		if _, err := tx.Exec(
			ctx,
			`INSERT INTO user_profile_search_outbox (
				event_id, user_id, profile_version, event_type, occurred_at,
				next_attempt_at
			) VALUES ($1, $2, $3, $4, $5, $5)
			ON CONFLICT DO NOTHING`,
			userProfileSearchProjectionEventID(
				projection.UserID,
				projection.ProfileVersion,
				projection.EventType,
			),
			projection.UserID,
			projection.ProfileVersion,
			projection.EventType,
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

func isUserProfileSearchProjectionEvent(eventType string) bool {
	switch eventType {
	case userevent.UserProfileUpdated,
		userevent.UserAvatarUpdated,
		userevent.UserRegistered:
		return true
	default:
		return false
	}
}

func userProfileCommandReceiptID(idempotencyKey string) string {
	digest := sha256.Sum256(
		[]byte("user-profile-command-receipt\x00" + idempotencyKey),
	)
	return hex.EncodeToString(digest[:])
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

func (s *PgProfileStore) IncrementCounter(ctx context.Context, userID, field string, delta int64) error {
	allowed := map[string]bool{
		"follower_count":  true,
		"following_count": true,
		"post_count":      true,
		"circle_count":    true,
		"like_count":      true,
	}
	if !allowed[field] {
		return fmt.Errorf("invalid counter field: %s", field)
	}
	query := fmt.Sprintf(
		`UPDATE user_profiles SET %s = GREATEST(%s + $1, 0), updated_at = NOW() WHERE user_id = $2`,
		field, field)
	_, err := s.pool.Exec(ctx, query, delta, userID)
	return err
}
