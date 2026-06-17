// Command seed loads user contract profile fixtures into the live PostgreSQL
// store so the local-gamma mirror can serve real "用户主页 / 我的主页" reads
// (GET /v1/user/profile/{userId} and GET /v1/me) for T3.
//
// User profiles live in PostgreSQL (table user_profiles), unlike circle data
// which lives in MongoDB. This seeder reuses the shared contract fixture loader
// and the generated user_profiles column set, mapping the curated fixture shape
// (displayName/stats.*) onto the persisted UserProfile columns so the row stays
// single-sourced with the service. Run from the quwoquan_service module:
//
//	go run ./services/user-service/cmd/seed \
//	  --pg-dsn 'postgres://quwoquan:quwoquan@localhost:19400/quwoquan?sslmode=disable' \
//	  --fixture user/test_fixtures/scenarios/user_scenarios.gamma-curated.json \
//	  --refs user_profile_core
package main

import (
	"context"
	"encoding/json"
	"flag"
	"log"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/runtime/contractfixture"
	model "quwoquan_service/services/user-service/internal/domain/user/model"
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
		IdentityOrigin:           "phone",
		LogicalShard:             0,
		AnonymousRetentionPolicy: "retain",
		// phone is UNIQUE + NOT-pointer in the model scan, so it must be a
		// distinct non-null value. It is json:"-" (never serialized to clients),
		// so a deterministic per-user sentinel is safe seed data.
		Phone:            "seed:" + fp.UserID,
		Nickname:         fp.DisplayName,
		AvatarURL:        fp.AvatarURL,
		AvatarAssetID:    avatarAssetID(fp),
		AvatarVersion:    avatarVersion(fp),
		Bio:              fp.Bio,
		IdentityTags:     "",
		Gender:           fp.Gender,
		BirthDate:        nil,
		Region:           fp.Region,
		Status:           "active",
		ProfileVersion:   1,
		FollowerCount:    fp.Stats.FollowerCount,
		FollowingCount:   fp.Stats.FollowingCount,
		PostCount:        fp.Stats.PostCount,
		CircleCount:      fp.Stats.CircleCount,
		LikeCount:        fp.Stats.LikeCount,
		OwnerDisplayName: fp.DisplayName,
		SubAccountCount:  0,
		CreatedAt:        now,
		UpdatedAt:        now,
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
	phone, nickname, avatar_url, avatar_asset_id, avatar_version, bio, identity_tags,
	gender, birth_date, region, status, profile_version, follower_count, following_count,
	post_count, circle_count, like_count, owner_display_name, sub_account_count,
	created_at, updated_at
) VALUES (
	$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18,
	$19, $20, $21, $22, $23, $24, $25, $26
)
ON CONFLICT (user_id) DO UPDATE SET
	account_state=EXCLUDED.account_state, identity_origin=EXCLUDED.identity_origin,
	logical_shard=EXCLUDED.logical_shard, anonymous_retention_policy=EXCLUDED.anonymous_retention_policy,
	phone=EXCLUDED.phone, nickname=EXCLUDED.nickname, avatar_url=EXCLUDED.avatar_url,
	avatar_asset_id=EXCLUDED.avatar_asset_id, avatar_version=EXCLUDED.avatar_version,
	bio=EXCLUDED.bio, identity_tags=EXCLUDED.identity_tags, gender=EXCLUDED.gender,
	birth_date=EXCLUDED.birth_date, region=EXCLUDED.region, status=EXCLUDED.status,
	profile_version=EXCLUDED.profile_version, follower_count=EXCLUDED.follower_count,
	following_count=EXCLUDED.following_count, post_count=EXCLUDED.post_count,
	circle_count=EXCLUDED.circle_count, like_count=EXCLUDED.like_count,
	owner_display_name=EXCLUDED.owner_display_name, sub_account_count=EXCLUDED.sub_account_count,
	updated_at=EXCLUDED.updated_at`

func upsertProfile(ctx context.Context, pool *pgxpool.Pool, p *model.UserProfile) error {
	_, err := pool.Exec(ctx, userProfileUpsert,
		p.UserID, p.AccountState, p.IdentityOrigin, p.LogicalShard, p.AnonymousRetentionPolicy,
		p.Phone, p.Nickname, p.AvatarURL, p.AvatarAssetID, p.AvatarVersion, p.Bio, p.IdentityTags,
		p.Gender, p.BirthDate, p.Region, p.Status, p.ProfileVersion, p.FollowerCount, p.FollowingCount,
		p.PostCount, p.CircleCount, p.LikeCount, p.OwnerDisplayName, p.SubAccountCount,
		p.CreatedAt, p.UpdatedAt,
	)
	return err
}

func main() {
	pgDSN := flag.String(
		"pg-dsn",
		"postgres://quwoquan:quwoquan@localhost:19400/quwoquan?sslmode=disable",
		"PostgreSQL DSN for the user store",
	)
	fixtureRel := flag.String(
		"fixture",
		"user/test_fixtures/scenarios/user_scenarios.gamma-curated.json",
		"metadata-relative user fixture path",
	)
	refsCSV := flag.String("refs", "user_profile_core", "comma-separated seed set refs")
	flag.Parse()

	pack, err := contractfixture.LoadMetadataJSON[userFixturePack](*fixtureRel)
	if err != nil {
		log.Fatalf("load user fixture %s: %v", *fixtureRel, err)
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, *pgDSN)
	if err != nil {
		log.Fatalf("connect postgres: %v", err)
	}
	defer pool.Close()

	// Reset previously seeded fixture rows so reseeding stays deterministic.
	if _, err := pool.Exec(ctx, `DELETE FROM user_profiles WHERE user_id LIKE 'fixture_%'`); err != nil {
		log.Fatalf("reset user_profiles: %v", err)
	}

	inserted := 0
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
			inserted++
		}
	}

	out, _ := json.Marshal(map[string]any{"insertedCount": inserted, "dsn": "postgres"})
	log.Printf("user seed done: %s", string(out))
}
