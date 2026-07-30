package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	userevent "quwoquan_service/services/user-service/internal/account/user_account/domain/user/event"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

// PersonaProfileProjector is the only runtime writer of UserAccount public
// profile columns. The Persona command transaction first persists authoritative
// state and a durable outbox coordinate; this projector then materializes the
// currently active Persona and checkpoints that coordinate in one transaction.
type PersonaProfileProjector struct {
	pool *pgxpool.Pool
}

var _ userports.PersonaProfileProjector = (*PersonaProfileProjector)(nil)

func NewPersonaProfileProjector(pool *pgxpool.Pool) (*PersonaProfileProjector, error) {
	if pool == nil {
		return nil, errors.New("Persona profile projector requires PostgreSQL pool")
	}
	return &PersonaProfileProjector{pool: pool}, nil
}

type personaPublicProfileState struct {
	PersonaID              string
	UserID                 string
	DisplayName            string
	NicknameCustomized     bool
	Bio                    string
	IdentityTags           []string
	TaxonomyReleaseID      string
	Gender                 string
	BirthDate              *string
	Region                 string
	RegionTagRef           string
	AvatarMediaAssetID     string
	AvatarURL              string
	AvatarVersion          int
	BackgroundMediaAssetID string
	BackgroundURL          string
	IsActive               bool
	Status                 string
	Version                int64
	UpdatedAt              time.Time
}

func (projector *PersonaProfileProjector) Project(
	ctx context.Context,
	personaID string,
	aggregateVersion int64,
) (*model.UserProfile, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" || aggregateVersion <= 0 {
		return nil, errors.New("Persona profile projection requires aggregate identity and version")
	}
	tx, err := projector.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return nil, fmt.Errorf("begin Persona profile projection: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	var projectedAt *time.Time
	var eventType string
	if err := tx.QueryRow(ctx, `
SELECT event_type, profile_projected_at
FROM personas_outbox
WHERE aggregate_id=$1 AND aggregate_version=$2
FOR UPDATE`, personaID, aggregateVersion).Scan(&eventType, &projectedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, fmt.Errorf(
				"Persona profile projection coordinate not found: %s@%d",
				personaID,
				aggregateVersion,
			)
		}
		return nil, fmt.Errorf("lock Persona profile projection coordinate: %w", err)
	}
	if !isPersonaPublicProfileEvent(eventType) {
		return nil, fmt.Errorf("unsupported Persona profile projection event: %s", eventType)
	}

	persona, err := loadPersonaPublicProfileState(ctx, tx, personaID)
	if err != nil {
		return nil, err
	}
	if projectedAt != nil {
		profile, err := loadUserProfileForProjection(ctx, tx, persona.UserID, false)
		if err != nil {
			return nil, err
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, fmt.Errorf("commit replayed Persona profile projection: %w", err)
		}
		return profile, nil
	}

	profile, err := loadUserProfileForProjection(ctx, tx, persona.UserID, true)
	if err != nil {
		return nil, err
	}
	if !persona.IsActive || strings.TrimSpace(persona.Status) == "retired" {
		if err := markPersonaProfileProjectionComplete(
			ctx,
			tx,
			persona.PersonaID,
			persona.Version,
		); err != nil {
			return nil, err
		}
		if err := tx.Commit(ctx); err != nil {
			return nil, fmt.Errorf("commit inactive Persona projection checkpoint: %w", err)
		}
		return profile, nil
	}

	oldAvatarURL := strings.TrimSpace(profile.AvatarURL)
	oldAvatarAssetID := strings.TrimSpace(profile.AvatarAssetID)
	nextProfileVersion := int64(profile.ProfileVersion) + 1
	if nextProfileVersion < persona.Version {
		nextProfileVersion = persona.Version
	}
	if nextProfileVersion <= 0 {
		nextProfileVersion = 1
	}
	projectionTime := persona.UpdatedAt.UTC()
	if projectionTime.IsZero() {
		projectionTime = time.Now().UTC()
	}

	if _, err := tx.Exec(ctx, `
UPDATE user_profiles
SET nickname=$2,
    nickname_customized=$3,
    avatar_url=$4,
    avatar_asset_id=$5,
    avatar_version=$6,
    background_url=$7,
    background_asset_id=$8,
    bio=$9,
    identity_tags=$10::text[]::text,
    gender=$11,
    birth_date=$12,
    region=$13,
    region_code=$14,
    profile_version=$15,
    owner_display_name=$2,
    updated_at=$16
WHERE user_id=$1`,
		persona.UserID,
		persona.DisplayName,
		persona.NicknameCustomized,
		persona.AvatarURL,
		persona.AvatarMediaAssetID,
		persona.AvatarVersion,
		persona.BackgroundURL,
		persona.BackgroundMediaAssetID,
		persona.Bio,
		persona.IdentityTags,
		persona.Gender,
		persona.BirthDate,
		persona.Region,
		persona.RegionTagRef,
		nextProfileVersion,
		projectionTime,
	); err != nil {
		return nil, fmt.Errorf("materialize active Persona profile: %w", err)
	}

	searchEvents := []userports.UserProfileSearchProjection{{
		UserID:         persona.UserID,
		ProfileVersion: nextProfileVersion,
		EventType:      userevent.UserProfileUpdated,
		OccurredAt:     projectionTime,
	}}
	if oldAvatarURL != strings.TrimSpace(persona.AvatarURL) ||
		oldAvatarAssetID != strings.TrimSpace(persona.AvatarMediaAssetID) {
		searchEvents = append(searchEvents, userports.UserProfileSearchProjection{
			UserID:         persona.UserID,
			ProfileVersion: nextProfileVersion,
			EventType:      userevent.UserAvatarUpdated,
			OccurredAt:     projectionTime,
		})
	}
	if err := appendUserProfileSearchProjections(ctx, tx, searchEvents); err != nil {
		return nil, err
	}
	if strings.TrimSpace(persona.TaxonomyReleaseID) != "" {
		if err := appendUserProfileTagProjection(ctx, tx, userports.UserProfileTagProjection{
			EventID:           personaProfileTagProjectionEventID(persona.UserID, nextProfileVersion),
			UserID:            persona.UserID,
			TagRefs:           append([]string(nil), persona.IdentityTags...),
			TaxonomyReleaseID: strings.TrimSpace(persona.TaxonomyReleaseID),
			ProfileVersion:    nextProfileVersion,
			OccurredAt:        projectionTime,
		}); err != nil {
			return nil, err
		}
	}
	if err := markPersonaProfileProjectionComplete(
		ctx,
		tx,
		persona.PersonaID,
		persona.Version,
	); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, fmt.Errorf("commit Persona profile projection: %w", err)
	}
	return projector.findProfile(ctx, persona.UserID)
}

func (projector *PersonaProfileProjector) ProjectNext(ctx context.Context) (bool, error) {
	var personaID string
	var aggregateVersion int64
	err := projector.pool.QueryRow(ctx, `
SELECT aggregate_id, aggregate_version
FROM personas_outbox
WHERE profile_projected_at IS NULL
  AND event_type = ANY($1::text[])
ORDER BY occurred_at, event_id
LIMIT 1`, personaPublicProfileEventTypes()).Scan(&personaID, &aggregateVersion)
	if errors.Is(err, pgx.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("find pending Persona profile projection: %w", err)
	}
	_, err = projector.Project(ctx, personaID, aggregateVersion)
	return true, err
}

func (projector *PersonaProfileProjector) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		return errors.New("Persona profile projector interval must be positive")
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		for {
			didWork, err := projector.ProjectNext(ctx)
			if err != nil {
				if ctx.Err() != nil {
					return ctx.Err()
				}
				slog.ErrorContext(ctx, "Persona profile projection failed", "error", err)
				break
			}
			if !didWork {
				break
			}
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func loadPersonaPublicProfileState(
	ctx context.Context,
	tx pgx.Tx,
	personaID string,
) (*personaPublicProfileState, error) {
	state := &personaPublicProfileState{}
	err := tx.QueryRow(ctx, `
SELECT persona_id, user_id, display_name, nickname_customized, bio,
       identity_tags, taxonomy_release_id, gender, birth_date::text, region,
       region_tag_ref, COALESCE(avatar_media_asset_id, ''), COALESCE(avatar_url, ''),
       avatar_version, COALESCE(background_media_asset_id, ''),
       COALESCE(background_url, ''), is_active,
       COALESCE(status, 'active'), version, updated_at
FROM personas
WHERE persona_id=$1
FOR SHARE`, personaID).Scan(
		&state.PersonaID,
		&state.UserID,
		&state.DisplayName,
		&state.NicknameCustomized,
		&state.Bio,
		&state.IdentityTags,
		&state.TaxonomyReleaseID,
		&state.Gender,
		&state.BirthDate,
		&state.Region,
		&state.RegionTagRef,
		&state.AvatarMediaAssetID,
		&state.AvatarURL,
		&state.AvatarVersion,
		&state.BackgroundMediaAssetID,
		&state.BackgroundURL,
		&state.IsActive,
		&state.Status,
		&state.Version,
		&state.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, fmt.Errorf("Persona profile projection source not found: %s", personaID)
	}
	if err != nil {
		return nil, fmt.Errorf("load Persona profile projection source: %w", err)
	}
	return state, nil
}

func loadUserProfileForProjection(
	ctx context.Context,
	tx pgx.Tx,
	userID string,
	lock bool,
) (*model.UserProfile, error) {
	query := `SELECT ` + userProfileNullableSafeCols + ` FROM user_profiles WHERE user_id=$1`
	if lock {
		query += ` FOR UPDATE`
	}
	profile, err := scanNullableSafeUserProfile(tx.QueryRow(ctx, query, userID))
	if err != nil {
		return nil, fmt.Errorf("load UserAccount profile projection: %w", err)
	}
	if profile == nil {
		return nil, fmt.Errorf("UserAccount profile projection target not found: %s", userID)
	}
	return profile, nil
}

func markPersonaProfileProjectionComplete(
	ctx context.Context,
	tx pgx.Tx,
	personaID string,
	throughVersion int64,
) error {
	if _, err := tx.Exec(ctx, `
UPDATE personas_outbox
SET profile_projected_at=NOW()
WHERE aggregate_id=$1
  AND aggregate_version <= $2
  AND profile_projected_at IS NULL
  AND event_type = ANY($3::text[])`,
		personaID,
		throughVersion,
		personaPublicProfileEventTypes(),
	); err != nil {
		return fmt.Errorf("checkpoint Persona profile projection: %w", err)
	}
	return nil
}

func (projector *PersonaProfileProjector) findProfile(
	ctx context.Context,
	userID string,
) (*model.UserProfile, error) {
	return scanNullableSafeUserProfile(projector.pool.QueryRow(
		ctx,
		`SELECT `+userProfileNullableSafeCols+` FROM user_profiles WHERE user_id=$1`,
		userID,
	))
}

func isPersonaPublicProfileEvent(eventType string) bool {
	switch eventType {
	case personaports.PersonaCreatedEvent,
		personaports.PersonaUpdatedEvent,
		personaports.PersonaRetiredEvent,
		personaports.PersonaActivatedEvent:
		return true
	default:
		return false
	}
}

func personaPublicProfileEventTypes() []string {
	return []string{
		personaports.PersonaCreatedEvent,
		personaports.PersonaUpdatedEvent,
		personaports.PersonaRetiredEvent,
		personaports.PersonaActivatedEvent,
	}
}

func personaProfileTagProjectionEventID(userID string, profileVersion int64) string {
	digest := sha256.Sum256([]byte(fmt.Sprintf(
		"persona-profile-tags\x00%s\x00%d",
		strings.TrimSpace(userID),
		profileVersion,
	)))
	return "ppt_" + hex.EncodeToString(digest[:24])
}
