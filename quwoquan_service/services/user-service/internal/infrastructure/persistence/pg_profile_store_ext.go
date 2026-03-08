package persistence

import (
	"context"
	"fmt"
	"time"

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
	return s.pgProfileStoreBase.Create(ctx, p)
}

// Update performs a selective update on editable profile fields and bumps version.
func (s *PgProfileStore) Update(ctx context.Context, p *model.UserProfile) error {
	p.UpdatedAt = time.Now().UTC()
	p.ProfileVersion++
	tag, err := s.pool.Exec(ctx, `
		UPDATE user_profiles
		SET nickname=$2, avatar_url=$3, bio=$4, gender=$5, birth_date=$6,
		    region=$7, profile_version=$8, updated_at=$9
		WHERE user_id=$1`,
		p.UserID, p.Nickname, p.AvatarURL, p.Bio, p.Gender,
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
