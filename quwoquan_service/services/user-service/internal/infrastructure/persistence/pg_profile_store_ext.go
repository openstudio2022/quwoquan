package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgProfileStore extends pgProfileStoreBase with domain-specific methods.
type PgProfileStore struct{ pgProfileStoreBase }

var _ repository.ProfileRepository = (*PgProfileStore)(nil)

func NewPgProfileStore(pool *pgxpool.Pool) *PgProfileStore {
	return &PgProfileStore{pgProfileStoreBase{pool: pool}}
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
	p.UpdatedAt = time.Now().UTC()
	p.ProfileVersion++
	tag, err := s.pool.Exec(ctx, `
		UPDATE user_profiles
		SET nickname=$2, avatar_url=$3, avatar_asset_id=$4, avatar_version=$5,
		    bio=$6, gender=$7, birth_date=$8, region=$9, profile_version=$10, updated_at=$11
		WHERE user_id=$1`,
		p.UserID, p.Nickname, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion, p.Bio, p.Gender,
		p.BirthDate, p.Region, p.ProfileVersion, p.UpdatedAt)
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
		`SELECT `+userProfileCols+` FROM user_profiles WHERE nickname = $1`, nickname)
	return scanUserProfile(row)
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
		`SELECT `+userProfileCols+`
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
		profile, err := scanUserProfileRow(rows)
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

func scanUserProfileRow(rows pgx.Rows) (*model.UserProfile, error) {
	e := &model.UserProfile{}
	err := rows.Scan(
		&e.UserID,
		&e.Phone,
		&e.Nickname,
		&e.AvatarURL,
		&e.AvatarAssetID,
		&e.AvatarVersion,
		&e.Bio,
		&e.Gender,
		&e.BirthDate,
		&e.Region,
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
	if err != nil {
		return nil, err
	}
	return e, nil
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
