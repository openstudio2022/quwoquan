// Command seed loads user contract profile fixtures into the live PostgreSQL
// store so the local-gamma mirror can serve real "用户主页 / 我的主页" reads
// (GET /user/profile/{userId} and GET /me) for T3.
//
// User profiles live in PostgreSQL (table user_profiles), unlike circle data
// which lives in MongoDB. This seeder reuses the shared contract fixture loader
// and the generated user_profiles column set, mapping the curated fixture shape
// (displayName/stats.*) onto the persisted UserProfile columns so the row stays
// single-sourced with the service. Run from the quwoquan_service module:
//
//	go run ./services/user-service/cmd/seed \
//	  --pg-dsn 'postgres://quwoquan:quwoquan@localhost:19400/quwoquan?sslmode=disable' \
//	  --fixture quwoquan_service/services/user-service/tests/support/contract_fixtures/scenarios/user_scenarios.gamma-curated.json \
//	  --refs user_profile_core
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"log"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/runtime/contractfixture"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	personaseed "quwoquan_service/services/user-service/internal/persona_management/persona/application/environmentseed"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
)

type userFixturePack struct {
	SeedSets map[string]userFixtureSeedSet `json:"seedSets"`
}

type userFixtureSeedSet struct {
	Profiles []userFixtureProfile `json:"profiles"`
}

type userFixtureProfile struct {
	UserID      string           `json:"userId"`
	DisplayName string           `json:"displayName"`
	AvatarURL   string           `json:"avatarUrl"`
	Bio         string           `json:"bio"`
	Region      string           `json:"region"`
	Gender      string           `json:"gender"`
	Stats       userFixtureStats `json:"stats"`
}

type userFixtureStats struct {
	FollowingCount int64 `json:"followingCount"`
	FollowerCount  int64 `json:"followerCount"`
	PostCount      int64 `json:"postCount"`
	CircleCount    int64 `json:"circleCount"`
	LikeCount      int64 `json:"likeCount"`
}

// profileFromFixture maps the curated fixture profile onto the persisted
// UserProfile model (generated user_profiles columns). Field names are taken
// from model.UserProfile so the mapping tracks the service schema.
func profileFromFixture(fp userFixtureProfile) *model.UserProfile {
	now := time.Now().UTC()
	return &model.UserProfile{
		UserID:                   fp.UserID,
		AccountState:             "active",
		IdentityOrigin:           "migrated_seed",
		LogicalShard:             0,
		AnonymousRetentionPolicy: "preserve",
		ProfileVersion:           0,
		PersonaCount:             1,
		CreatedAt:                now,
		UpdatedAt:                now,
	}
}

func avatarAssetID(fp userFixtureProfile) string {
	if fp.AvatarURL == "" {
		return ""
	}
	return "ua_" + fp.UserID
}

func avatarVersion(fp userFixtureProfile) int {
	if fp.AvatarURL == "" {
		return 0
	}
	return 1
}

// userProfileColumns mirrors the generated userProfileCols const in
// pg_profile_store.g.go. Kept here so the seeder upsert stays column-aligned.
const userProfileUpsert = `
INSERT INTO user_profiles (
	user_id, account_state, identity_origin, logical_shard, anonymous_retention_policy,
	phone, nickname, nickname_customized, avatar_version, profile_version,
	owner_display_name, persona_count, created_at, updated_at
) VALUES (
	$1, $2, $3, $4, $5, NULL, '', false, 0, 0, '', $6, $7, $8
)
ON CONFLICT (user_id) DO UPDATE SET
	account_state=EXCLUDED.account_state, identity_origin=EXCLUDED.identity_origin,
	logical_shard=EXCLUDED.logical_shard, anonymous_retention_policy=EXCLUDED.anonymous_retention_policy,
	persona_count=EXCLUDED.persona_count,
	updated_at=EXCLUDED.updated_at`

func upsertProfile(ctx context.Context, pool *pgxpool.Pool, p *model.UserProfile) error {
	_, err := pool.Exec(ctx, userProfileUpsert,
		p.UserID, p.AccountState, p.IdentityOrigin, p.LogicalShard, p.AnonymousRetentionPolicy,
		p.PersonaCount, p.CreatedAt, p.UpdatedAt,
	)
	return err
}

func seedPrimaryPersona(
	ctx context.Context,
	store *personapersistence.PersonaCommandPostgresStore,
	persona *model.Persona,
) (personaports.PersonaCommandResult, error) {
	payload, err := json.Marshal(persona)
	if err != nil {
		return personaports.PersonaCommandResult{}, err
	}
	sum := sha256.Sum256(payload)
	return store.CommitCreate(ctx, persona, personaports.PersonaCommandMeta{
		IdempotencyKey: "environment-seed:primary-persona:" + persona.PersonaID,
		CommandDigest:  hex.EncodeToString(sum[:]),
	})
}

func main() {
	pgDSN := flag.String(
		"pg-dsn",
		"postgres://quwoquan:quwoquan@localhost:19400/quwoquan?sslmode=disable",
		"PostgreSQL DSN for the user store",
	)
	fixtureRel := flag.String(
		"fixture",
		"quwoquan_service/services/user-service/tests/support/contract_fixtures/scenarios/user_scenarios.gamma-curated.json",
		"metadata-relative user fixture path",
	)
	refsCSV := flag.String("refs", "user_profile_core", "comma-separated seed set refs")
	flag.Parse()

	pack, err := contractfixture.LoadRepositoryJSON[userFixturePack](*fixtureRel)
	if err != nil {
		log.Fatalf("load user fixture %s: %v", *fixtureRel, err)
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, *pgDSN)
	if err != nil {
		log.Fatalf("connect postgres: %v", err)
	}
	defer pool.Close()
	personaStore, err := personapersistence.NewPersonaCommandPostgresStore(pool)
	if err != nil {
		log.Fatalf("open persona command store: %v", err)
	}
	personaProjector, err := useraccountpersistence.NewPersonaProfileProjector(pool)
	if err != nil {
		log.Fatalf("open persona profile projector: %v", err)
	}

	// Reset the complete fixture-owned command history before deleting profiles.
	// Persona receipts/outbox records do not reference user_profiles, so leaving
	// them behind would make the next deterministic seed replay a successful
	// historical command without recreating the deleted aggregate.
	for _, statement := range []struct {
		name string
		sql  string
	}{
		{
			name: "personas_command_receipts",
			sql:  `DELETE FROM personas_command_receipts WHERE aggregate_id LIKE 'fixture_%'`,
		},
		{
			name: "personas_outbox",
			sql:  `DELETE FROM personas_outbox WHERE aggregate_id LIKE 'fixture_%'`,
		},
		{
			name: "user_profiles",
			sql:  `DELETE FROM user_profiles WHERE user_id LIKE 'fixture_%'`,
		},
	} {
		if _, err := pool.Exec(ctx, statement.sql); err != nil {
			log.Fatalf("reset %s: %v", statement.name, err)
		}
	}

	inserted := 0
	personasInserted := 0
	for _, ref := range strings.Split(*refsCSV, ",") {
		ref = strings.TrimSpace(ref)
		seedSet, ok := pack.SeedSets[ref]
		if !ok {
			log.Printf("WARN: seed ref not found: %s", ref)
			continue
		}
		for _, fp := range seedSet.Profiles {
			if strings.TrimSpace(fp.UserID) == "" {
				continue
			}
			if err := upsertProfile(ctx, pool, profileFromFixture(fp)); err != nil {
				log.Fatalf("upsert profile %s: %v", fp.UserID, err)
			}
			personaResult, err := seedPrimaryPersona(
				ctx,
				personaStore,
				personaseed.BuildPrimaryPersona(personaseed.PrimaryPersonaInput{
					UserID:             fp.UserID,
					DisplayName:        fp.DisplayName,
					AvatarMediaAssetID: avatarAssetID(fp),
					AvatarURL:          fp.AvatarURL,
					AvatarVersion:      avatarVersion(fp),
					Bio:                fp.Bio,
					Gender:             fp.Gender,
					Region:             fp.Region,
				}),
			)
			if err != nil {
				log.Fatalf("seed primary persona %s: %v", fp.UserID, err)
			}
			if _, err := personaProjector.Project(
				ctx,
				personaResult.PersonaID,
				personaResult.Version,
			); err != nil {
				log.Fatalf("project primary persona %s: %v", fp.UserID, err)
			}
			inserted++
			personasInserted++
		}
	}

	out, _ := json.Marshal(map[string]any{
		"insertedCount":       inserted,
		"primaryPersonaCount": personasInserted,
		"dsn":                 "postgres",
	})
	log.Printf("user seed done: %s", string(out))
}
