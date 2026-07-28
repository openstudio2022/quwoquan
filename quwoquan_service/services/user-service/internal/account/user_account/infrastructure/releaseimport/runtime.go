// Package releaseimport materializes the public creator projection of one
// immutable Data release. It never creates credentials or modifies accounts
// that are not explicitly owned by the Data release.
package releaseimport

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemedia "quwoquan_service/runtime/media"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

const (
	releaseSchema       = "quwoquan_data.release_desired_state"
	reportSchema        = "quwoquan.user_creator_import_report"
	dataSourceOwner     = "qwq_data"
	contentIdentityKind = "content_release"
	projectionDatabase  = "quwoquan_user"
	modeUpsert          = "upsert"
	modeSync            = "sync"
)

type desiredState struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	DesiredRefs struct {
		Creators []string `json:"creators"`
	} `json:"desiredRefs"`
}

type creatorProfile struct {
	Schema               string                `json:"schema"`
	CreatorID            string                `json:"creatorId"`
	UserID               string                `json:"userId"`
	AuthorID             string                `json:"authorId"`
	SubAccountID         string                `json:"subAccountId"`
	DisplayName          string                `json:"displayName"`
	UserHandle           string                `json:"userHandle"`
	AvatarAsset          *creatorMediaAssetRef `json:"avatarAsset"`
	AvatarObjectKey      string                `json:"avatarObjectKey"`
	AvatarURL            string                `json:"-"`
	AvatarVersion        int64                 `json:"-"`
	AvatarPublicSliceKey string                `json:"-"`
	Headline             string                `json:"headline"`
	Bio                  string                `json:"bio"`
	CreatorArchetype     string                `json:"creatorArchetype"`
	PublicProfileTagRefs []string              `json:"publicProfileTagRefs"`
}

type creatorMediaAssetRef struct {
	AssetID   string `json:"assetId"`
	Kind      string `json:"kind"`
	SHA256    string `json:"sha256"`
	ObjectKey string `json:"objectKey"`
}

type creatorRecord struct {
	Profile creatorProfile
	Works   []model.CreatorWorkRef
}

type importReport struct {
	Schema             string   `json:"schema"`
	Status             string   `json:"status"`
	Environment        string   `json:"environment"`
	ReleaseID          string   `json:"releaseId"`
	SourceOwner        string   `json:"sourceOwner"`
	Mode               string   `json:"mode"`
	ProjectionDatabase string   `json:"projectionDatabase"`
	Counts             counts   `json:"counts"`
	AuthorIDs          []string `json:"authorIds"`
	VerifiedCreatorIDs []string `json:"verifiedCreatorIds"`
	GeneratedAt        string   `json:"generatedAt"`
}

type counts struct {
	CreatorsLoaded   int `json:"creatorsLoaded"`
	UsersUpserted    int `json:"usersUpserted"`
	CreatorsUpserted int `json:"creatorsUpserted"`
	UsersRemoved     int `json:"usersRemoved"`
	CreatorsRemoved  int `json:"creatorsRemoved"`
}

func Run() {
	releaseRoot := flag.String("release-root", "", "immutable release root (required)")
	postgresDSN := flag.String("postgres-dsn", "", "user-service PostgreSQL DSN (required)")
	mongoURI := flag.String("mongo-uri", "", "user-service MongoDB URI (required)")
	mediaAvatarBaseURL := flag.String("media-avatar-base-url", "", "avatar media public base URL")
	environment := flag.String("env", "", "environment label (required)")
	mode := flag.String("mode", modeUpsert, "apply mode: upsert|sync")
	reportPath := flag.String("report", "", "machine-readable report path (required)")
	dryRun := flag.Bool("dry-run", false, "validate release without writes")
	flag.Parse()

	if err := requireArguments(*releaseRoot, *postgresDSN, *mongoURI, *environment, *reportPath, *mode); err != nil {
		fatal(err)
	}
	state, creators, err := loadCreators(*releaseRoot, *mediaAvatarBaseURL)
	if err != nil {
		fatal(err)
	}
	report := importReport{
		Schema: reportSchema, Status: "dry-run", Environment: *environment,
		ReleaseID: state.ReleaseID, SourceOwner: dataSourceOwner, Mode: *mode,
		ProjectionDatabase: projectionDatabase,
		Counts:             counts{CreatorsLoaded: len(creators)},
		AuthorIDs:          authorIDs(creators),
		VerifiedCreatorIDs: []string{},
		GeneratedAt:        time.Now().UTC().Format(time.RFC3339),
	}
	if *dryRun {
		fatal(writeReport(*reportPath, report))
		return
	}

	ctx := context.Background()
	pool, err := pgxpool.New(ctx, *postgresDSN)
	if err != nil {
		fatal(fmt.Errorf("connect user postgres: %w", err))
	}
	defer pool.Close()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		fatal(fmt.Errorf("connect user mongo: %w", err))
	}
	defer client.Disconnect(ctx)

	if err := assertNoForeignUserCollision(ctx, pool, creators); err != nil {
		fatal(err)
	}
	usersUpserted, err := upsertUsers(ctx, pool, creators)
	if err != nil {
		fatal(err)
	}
	projectionDB := client.Database(projectionDatabase)
	creatorsUpserted, err := upsertCreatorProfiles(ctx, projectionDB, creators, state.ReleaseID)
	if err != nil {
		fatal(err)
	}
	verifiedCreatorIDs, err := verifyCreatorProfileReadback(
		ctx,
		projectionDB,
		creators,
		state.ReleaseID,
	)
	if err != nil {
		fatal(err)
	}
	report.Counts.UsersUpserted = usersUpserted
	report.Counts.CreatorsUpserted = creatorsUpserted
	report.VerifiedCreatorIDs = verifiedCreatorIDs
	if *mode == modeSync {
		report.Counts.UsersRemoved, err = removeAbsentUsers(ctx, pool, report.AuthorIDs)
		if err != nil {
			fatal(err)
		}
		report.Counts.CreatorsRemoved, err = removeAbsentCreatorProfiles(ctx, projectionDB, creatorIDs(creators))
		if err != nil {
			fatal(err)
		}
	}
	report.Status = "active"
	report.GeneratedAt = time.Now().UTC().Format(time.RFC3339)
	fatal(writeReport(*reportPath, report))
}

func requireArguments(values ...string) error {
	for _, value := range values[:5] {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("release importer requires release root, postgres DSN, mongo URI, environment and report path")
		}
	}
	if values[5] != modeUpsert && values[5] != modeSync {
		return fmt.Errorf("release importer mode must be %q or %q", modeUpsert, modeSync)
	}
	return nil
}

func loadCreators(
	releaseRoot string,
	mediaAvatarBaseURL string,
) (desiredState, []creatorRecord, error) {
	statePath := filepath.Join(releaseRoot, "payload", "desired_state.json")
	bytes, err := os.ReadFile(statePath)
	if err != nil {
		return desiredState{}, nil, fmt.Errorf("read desired state: %w", err)
	}
	var state desiredState
	if err := json.Unmarshal(bytes, &state); err != nil {
		return desiredState{}, nil, fmt.Errorf("decode desired state: %w", err)
	}
	if state.Schema != releaseSchema || strings.TrimSpace(state.ReleaseID) == "" {
		return desiredState{}, nil, fmt.Errorf("invalid immutable release desired state")
	}
	releaseAssets, err := runtimemedia.LoadReleaseMediaAssets(releaseRoot, state.ReleaseID)
	if err != nil {
		return desiredState{}, nil, fmt.Errorf("load release media authority: %w", err)
	}
	records := make([]creatorRecord, 0, len(state.DesiredRefs.Creators))
	seen := make(map[string]struct{}, len(state.DesiredRefs.Creators))
	for _, ref := range state.DesiredRefs.Creators {
		if err := safeRef(ref); err != nil {
			return desiredState{}, nil, err
		}
		if _, exists := seen[ref]; exists {
			return desiredState{}, nil, fmt.Errorf("duplicate creator desired ref: %s", ref)
		}
		seen[ref] = struct{}{}
		root := filepath.Join(releaseRoot, "payload", "objects", "creators", ref)
		profile, err := loadCreatorProfile(root, ref)
		if err != nil {
			return desiredState{}, nil, err
		}
		if profile.AvatarAsset != nil {
			resolved, resolveErr := runtimemedia.ResolveReleaseMediaAsset(
				releaseAssets,
				runtimemedia.MediaDeliveryBases{Avatar: mediaAvatarBaseURL},
				profile.AvatarAsset.AssetID,
				profile.AvatarAsset.Kind,
				profile.AvatarAsset.SHA256,
				"creators/"+ref,
			)
			if resolveErr != nil {
				return desiredState{}, nil, fmt.Errorf(
					"creator %s avatar differs from release media authority: %w",
					ref,
					resolveErr,
				)
			}
			profile.AvatarURL = resolved.PublicURL
			profile.AvatarVersion = resolved.Version
			profile.AvatarPublicSliceKey = resolved.PublicSliceKey
		}
		works, err := loadCreatorWorks(filepath.Join(root, "works.refs.ndjson"))
		if err != nil {
			return desiredState{}, nil, err
		}
		records = append(records, creatorRecord{Profile: profile, Works: works})
	}
	sort.Slice(records, func(left, right int) bool {
		return records[left].Profile.CreatorID < records[right].Profile.CreatorID
	})
	return state, records, nil
}

func safeRef(ref string) error {
	clean := filepath.Clean(filepath.FromSlash(strings.TrimSpace(ref)))
	if ref == "" || filepath.IsAbs(clean) || clean == "." || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return fmt.Errorf("unsafe creator desired ref: %q", ref)
	}
	return nil
}

func loadCreatorProfile(root, ref string) (creatorProfile, error) {
	path := filepath.Join(root, "profile.json")
	bytes, err := os.ReadFile(path)
	if err != nil {
		return creatorProfile{}, fmt.Errorf("read creator profile %s: %w", ref, err)
	}
	var profile creatorProfile
	if err := json.Unmarshal(bytes, &profile); err != nil {
		return creatorProfile{}, fmt.Errorf("decode creator profile %s: %w", ref, err)
	}
	if strings.TrimSpace(profile.AvatarObjectKey) != "" ||
		(profile.AvatarAsset != nil && strings.TrimSpace(profile.AvatarAsset.ObjectKey) != "") {
		return creatorProfile{}, fmt.Errorf(
			"creator profile %s contains forbidden avatar objectKey",
			ref,
		)
	}
	if profile.Schema != "quwoquan_data.creator_profile" || profile.CreatorID != ref ||
		profile.UserID == "" || profile.AuthorID == "" || profile.UserID != profile.AuthorID ||
		profile.SubAccountID == "" || profile.DisplayName == "" {
		return creatorProfile{}, fmt.Errorf("invalid creator profile: %s", ref)
	}
	return profile, nil
}

func loadCreatorWorks(path string) ([]model.CreatorWorkRef, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("read creator works: %w", err)
	}
	defer file.Close()
	works := []model.CreatorWorkRef{}
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var work model.CreatorWorkRef
		if err := json.Unmarshal([]byte(line), &work); err != nil || strings.TrimSpace(work.Ref) == "" {
			return nil, fmt.Errorf("invalid creator work reference: %s", path)
		}
		works = append(works, work)
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("scan creator works: %w", err)
	}
	return works, nil
}

func assertNoForeignUserCollision(ctx context.Context, pool *pgxpool.Pool, creators []creatorRecord) error {
	for _, creator := range creators {
		var origin string
		err := pool.QueryRow(ctx, "SELECT identity_origin FROM user_profiles WHERE user_id=$1", creator.Profile.UserID).Scan(&origin)
		if err != nil && err != pgx.ErrNoRows {
			return fmt.Errorf("lookup creator user %s: %w", creator.Profile.UserID, err)
		}
		if err == nil && origin != contentIdentityKind {
			return fmt.Errorf("creator userId collides with non-release account: %s", creator.Profile.UserID)
		}
	}
	return nil
}

func upsertUsers(ctx context.Context, pool *pgxpool.Pool, creators []creatorRecord) (int, error) {
	const query = `INSERT INTO user_profiles (
		user_id, account_state, identity_origin, logical_shard, anonymous_retention_policy,
		phone, nickname, avatar_url, avatar_asset_id, avatar_version, bio, identity_tags,
		status, profile_version, owner_display_name, sub_account_count, created_at, updated_at
	) VALUES ($1, 'active', 'content_release', 0, 'preserve', NULL, $2, $3, $4, $5, $6, '', 'active', 1, $2, 0, NOW(), NOW())
	ON CONFLICT (user_id) DO UPDATE SET nickname=EXCLUDED.nickname,
		avatar_url=EXCLUDED.avatar_url, avatar_asset_id=EXCLUDED.avatar_asset_id,
		avatar_version=EXCLUDED.avatar_version, bio=EXCLUDED.bio,
		owner_display_name=EXCLUDED.owner_display_name, updated_at=NOW()
	WHERE user_profiles.identity_origin='content_release'`
	count := 0
	for _, creator := range creators {
		profile := creator.Profile
		avatarAssetID := ""
		if profile.AvatarAsset != nil {
			avatarAssetID = profile.AvatarAsset.AssetID
		}
		tag, err := pool.Exec(
			ctx,
			query,
			profile.UserID,
			profile.DisplayName,
			nullableString(profile.AvatarURL),
			nullableString(avatarAssetID),
			profile.AvatarVersion,
			profile.Bio,
		)
		if err != nil {
			return 0, fmt.Errorf("upsert creator user %s: %w", creator.Profile.UserID, err)
		}
		if tag.RowsAffected() != 1 {
			return 0, fmt.Errorf("creator user not owned by release: %s", creator.Profile.UserID)
		}
		count++
	}
	return count, nil
}

func nullableString(value string) any {
	if strings.TrimSpace(value) == "" {
		return nil
	}
	return value
}

func upsertCreatorProfiles(ctx context.Context, database *mongo.Database, creators []creatorRecord, releaseID string) (int, error) {
	collection := database.Collection("creator_runtime_profiles")
	count := 0
	for _, creator := range creators {
		profile := creator.Profile
		runtime := model.CreatorRuntimeProfile{
			CreatorID: profile.CreatorID, SubAccountID: profile.SubAccountID, Handle: profile.UserHandle,
			DisplayName: profile.DisplayName, Headline: profile.Headline, Bio: profile.Bio,
			AvatarURL: profile.AvatarURL, AvatarVersion: profile.AvatarVersion,
			AvatarPublicSliceKey: profile.AvatarPublicSliceKey,
			PublicProfileTagRefs: profile.PublicProfileTagRefs,
			CreatorArchetype:     profile.CreatorArchetype, Works: creator.Works, PackageDigest: releaseID,
			ReleaseID: releaseID, Status: "active", ManagedBy: dataSourceOwner,
			ImportedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC(),
		}
		if profile.AvatarAsset != nil {
			runtime.AvatarAssetID = profile.AvatarAsset.AssetID
			runtime.AvatarSHA256 = profile.AvatarAsset.SHA256
		}
		_, err := collection.UpdateOne(ctx, bson.M{"creatorId": profile.CreatorID}, bson.M{"$set": runtime}, options.UpdateOne().SetUpsert(true))
		if err != nil {
			return 0, fmt.Errorf("upsert creator runtime profile %s: %w", profile.CreatorID, err)
		}
		count++
	}
	return count, nil
}

func verifyCreatorProfileReadback(
	ctx context.Context,
	database *mongo.Database,
	creators []creatorRecord,
	releaseID string,
) ([]string, error) {
	collection := database.Collection("creator_runtime_profiles")
	verified := make([]string, 0, len(creators))
	for _, creator := range creators {
		profile := creator.Profile
		var persisted model.CreatorRuntimeProfile
		err := collection.FindOne(ctx, bson.M{
			"creatorId":    profile.CreatorID,
			"subAccountId": profile.SubAccountID,
			"releaseId":    releaseID,
			"managedBy":    dataSourceOwner,
			"status":       "active",
		}).Decode(&persisted)
		if err != nil {
			return nil, fmt.Errorf(
				"read back creator projection %s from %s: %w",
				profile.CreatorID,
				projectionDatabase,
				err,
			)
		}
		if persisted.CreatorID != profile.CreatorID ||
			persisted.SubAccountID != profile.SubAccountID {
			return nil, fmt.Errorf(
				"creator projection identity drift after readback: %s",
				profile.CreatorID,
			)
		}
		verified = append(verified, persisted.CreatorID)
	}
	sort.Strings(verified)
	return verified, nil
}

func removeAbsentUsers(ctx context.Context, pool *pgxpool.Pool, authorIDs []string) (int, error) {
	tag, err := pool.Exec(ctx, "DELETE FROM user_profiles WHERE identity_origin='content_release' AND NOT (user_id = ANY($1))", authorIDs)
	if err != nil {
		return 0, fmt.Errorf("remove absent release users: %w", err)
	}
	return int(tag.RowsAffected()), nil
}

func removeAbsentCreatorProfiles(ctx context.Context, database *mongo.Database, ids []string) (int, error) {
	result, err := database.Collection("creator_runtime_profiles").DeleteMany(ctx, bson.M{
		"managedBy": dataSourceOwner,
		"creatorId": bson.M{"$nin": ids},
	})
	if err != nil {
		return 0, fmt.Errorf("remove absent creator runtime profiles: %w", err)
	}
	return int(result.DeletedCount), nil
}

func authorIDs(creators []creatorRecord) []string {
	ids := make([]string, 0, len(creators))
	for _, creator := range creators {
		ids = append(ids, creator.Profile.AuthorID)
	}
	sort.Strings(ids)
	return ids
}

func creatorIDs(creators []creatorRecord) []string {
	ids := make([]string, 0, len(creators))
	for _, creator := range creators {
		ids = append(ids, creator.Profile.CreatorID)
	}
	sort.Strings(ids)
	return ids
}

func writeReport(path string, report importReport) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return fmt.Errorf("create report directory: %w", err)
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("open report: %w", err)
	}
	defer file.Close()
	return json.NewEncoder(file).Encode(report)
}

func fatal(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "release creator import:", err)
		os.Exit(1)
	}
}
