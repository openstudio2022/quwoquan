package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	repository "quwoquan_service/services/user-service/internal/domain/user/ports"
)

// PgProfileStore extends pgProfileStoreBase with domain-specific methods.
type PgProfileStore struct{ pgProfileStoreBase }

var _ repository.UserProfileStore = (*PgProfileStore)(nil)

func NewPgProfileStore(pool *pgxpool.Pool) *PgProfileStore {
	return &PgProfileStore{pgProfileStoreBase{pool: pool}}
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
	return s.pgProfileStoreBase.Create(ctx, p)
}

// Update performs a selective update on editable profile fields and bumps version.
func (s *PgProfileStore) Update(ctx context.Context, p *model.UserProfile) error {
	if p.UpdatedAt.IsZero() {
		p.UpdatedAt = time.Now().UTC()
	}
	tag, err := s.pool.Exec(ctx, `
		UPDATE user_profiles
			SET nickname=$2, nickname_customized=$3, avatar_url=$4, avatar_asset_id=$5, avatar_version=$6,
			    background_url=$7, background_asset_id=$8, bio=$9, gender=$10, birth_date=$11,
			    region=$12, region_code=$13, profile_version=$14, updated_at=$15
			WHERE user_id=$1`,
		p.UserID, p.Nickname, p.NicknameCustomized, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion,
		p.BackgroundURL, p.BackgroundAssetID, p.Bio, p.Gender, p.BirthDate, p.Region, p.RegionCode, p.ProfileVersion, p.UpdatedAt)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("profile not found: %s", p.UserID)
	}
	return nil
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
