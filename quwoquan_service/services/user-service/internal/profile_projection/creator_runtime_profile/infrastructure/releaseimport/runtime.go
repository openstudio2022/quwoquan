// Package releaseimport stages the Creator owner-local projection of one
// immutable Data release. It never writes PostgreSQL UserAccount/Persona state,
// Persona outbox/receipts, or a mutable active/latest pointer.
package releaseimport

import (
	"bufio"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/datarelease"
	runtimemedia "quwoquan_service/runtime/media"
	model "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
	creatorpersistence "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/persistence"
)

const (
	releaseSchema       = "quwoquan_data.release_desired_state"
	reportSchema        = "quwoquan.user_creator_import_report"
	dataSourceOwner     = "qwq_data"
	projectionDatabase  = "quwoquan_user"
	projectionVersion   = int64(1)
	activationStageOnly = "stage-only"
)

type desiredState struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	DesiredRefs struct {
		Creators []string `json:"creators"`
	} `json:"desiredRefs"`
}

type creatorProfile struct {
	Schema               string                  `json:"schema"`
	CreatorID            string                  `json:"creatorId"`
	UserID               string                  `json:"userId"`
	AuthorID             string                  `json:"authorId"`
	PersonaID            string                  `json:"personaId"`
	DisplayName          string                  `json:"displayName"`
	UserHandle           string                  `json:"userHandle"`
	AvatarAsset          *creatorMediaAssetRef   `json:"avatarAsset"`
	AvatarObjectKey      string                  `json:"avatarObjectKey"`
	AvatarURL            string                  `json:"-"`
	AvatarVersion        int64                   `json:"-"`
	AvatarPublicSliceKey string                  `json:"-"`
	Headline             string                  `json:"headline"`
	Bio                  string                  `json:"bio"`
	CreatorArchetype     string                  `json:"creatorArchetype"`
	PublicProfileTagRefs []string                `json:"publicProfileTagRefs"`
	Disclosure           model.CreatorDisclosure `json:"disclosure"`
}

type creatorMediaAssetRef struct {
	AssetID   string `json:"assetId"`
	Kind      string `json:"kind"`
	SHA256    string `json:"sha256"`
	ObjectKey string `json:"objectKey"`
}

type creatorRecord struct {
	Profile       creatorProfile
	ProfileDigest string
	Works         []model.CreatorWorkRef
}

type importReport struct {
	Schema             string                               `json:"schema"`
	Status             string                               `json:"status"`
	Environment        string                               `json:"environment"`
	ReleaseID          string                               `json:"releaseId"`
	SourceOwner        string                               `json:"sourceOwner"`
	ManifestDigest     string                               `json:"manifestDigest"`
	ActivationMode     string                               `json:"activationMode"`
	ProjectionDatabase string                               `json:"projectionDatabase"`
	ProjectionVersion  int64                                `json:"projectionVersion,omitempty"`
	ClosureDigest      string                               `json:"closureDigest,omitempty"`
	VerifiedAt         *time.Time                           `json:"verifiedAt,omitempty"`
	Counts             counts                               `json:"counts"`
	AuthorIDs          []string                             `json:"authorIds"`
	ProfileDigests     []model.CreatorProfileDigestBinding  `json:"profileDigests"`
	VerifiedCreatorIDs []string                             `json:"verifiedCreatorIds"`
	PostgreSQLWrites   model.CandidatePostgreSQLWriteCounts `json:"postgresqlWrites"`
	GeneratedAt        string                               `json:"generatedAt"`
}

type counts struct {
	CreatorsExpected  int `json:"creatorsExpected"`
	CreatorsProjected int `json:"creatorsProjected"`
	UsersUpserted     int `json:"usersUpserted"`
	PersonasUpserted  int `json:"personasUpserted"`
}

// Run stages a Creator candidate. --postgres-dsn, --run-id and --mode are
// accepted as deprecated compatibility seams but can never trigger PG writes.
func Run() {
	set := flag.NewFlagSet("release-import", flag.ExitOnError)
	releaseRoot := set.String("release-root", "", "immutable release root (required)")
	_ = set.String("postgres-dsn", "", "deprecated compatibility seam; ignored")
	mongoURI := set.String("mongo-uri", "", "user-service MongoDB URI (required)")
	mediaAvatarBaseURL := set.String("media-avatar-base-url", "", "avatar media public base URL")
	environment := set.String("env", "", "environment label (required)")
	_ = set.String("run-id", "", "deprecated compatibility seam; ignored")
	_ = set.String("mode", "upsert", "deprecated compatibility seam; ignored")
	activationMode := set.String("activation-mode", activationStageOnly, "only stage-only is supported")
	reportPath := set.String("report", "", "machine-readable create-once report path (required)")
	dryRun := set.Bool("dry-run", false, "validate release without writes")
	_ = set.Parse(os.Args[1:])

	if strings.TrimSpace(*releaseRoot) == "" || strings.TrimSpace(*mongoURI) == "" || strings.TrimSpace(*environment) == "" || strings.TrimSpace(*reportPath) == "" {
		fatal(fmt.Errorf("release importer requires release root, mongo URI, environment and report path"))
	}
	if strings.TrimSpace(*activationMode) != activationStageOnly {
		fatal(fmt.Errorf("Creator release importer supports only --activation-mode=stage-only"))
	}
	tuple, err := datarelease.Load(*releaseRoot)
	if err != nil {
		fatal(fmt.Errorf("verify immutable release identity: %w", err))
	}
	state, creators, err := LoadCreatorsForRelease(*releaseRoot, *mediaAvatarBaseURL)
	if err != nil {
		fatal(err)
	}
	if state.ReleaseID != tuple.ReleaseID || tuple.SourceOwner != datarelease.SourceOwnerQWQData {
		fatal(fmt.Errorf("desired state differs from immutable release identity"))
	}
	identity := model.ReleaseIdentity{Environment: strings.TrimSpace(*environment), SourceOwner: string(tuple.SourceOwner), ReleaseID: tuple.ReleaseID, ManifestDigest: string(tuple.PayloadSHA256)}
	generatedAt := time.Now().UTC().Truncate(time.Millisecond)
	projections, candidate, err := buildCandidate(identity, creators, generatedAt)
	if err != nil {
		fatal(err)
	}
	report := candidateImportReport(candidate, creatorIDs(creators), *dryRun, generatedAt)
	if *dryRun {
		fatal(WriteCreateOnceReport(*reportPath, report))
		return
	}
	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		fatal(fmt.Errorf("connect user MongoDB: %w", err))
	}
	defer client.Disconnect(ctx)
	store := creatorpersistence.NewCreatorReleaseCandidateStore(client.Database(projectionDatabase))
	if err := store.EnsureIndexes(ctx); err != nil {
		fatal(err)
	}
	if _, err := store.Stage(ctx, candidate, projections); err != nil {
		fatal(err)
	}
	readback, found, err := store.ReadVerifiedCandidate(ctx, identity)
	if err != nil || !found {
		fatal(fmt.Errorf("read back verified Creator release candidate: found=%v err=%w", found, err))
	}
	report = candidateImportReport(readback, creatorIDs(creators), false, generatedAt)
	fatal(WriteCreateOnceReport(*reportPath, report))
}

// LoadCreatorsForRelease validates and projects creator objects without writes.
func LoadCreatorsForRelease(releaseRoot, mediaAvatarBaseURL string) (desiredState, []creatorRecord, error) {
	statePath := filepath.Join(releaseRoot, "payload", "desired_state.json")
	raw, err := os.ReadFile(statePath)
	if err != nil {
		return desiredState{}, nil, fmt.Errorf("read desired state: %w", err)
	}
	var state desiredState
	if err := json.Unmarshal(raw, &state); err != nil {
		return desiredState{}, nil, fmt.Errorf("decode desired state: %w", err)
	}
	if state.Schema != releaseSchema || strings.TrimSpace(state.ReleaseID) == "" {
		return desiredState{}, nil, fmt.Errorf("invalid immutable release desired state")
	}
	releaseClass, err := loadReleaseClass(releaseRoot)
	if err != nil {
		return desiredState{}, nil, err
	}
	releaseAssets, err := runtimemedia.LoadReleaseMediaAssets(releaseRoot, state.ReleaseID, releaseClass)
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
		profile, profileDigest, err := loadCreatorProfile(root, ref)
		if err != nil {
			return desiredState{}, nil, err
		}
		if profile.AvatarAsset != nil {
			resolved, resolveErr := runtimemedia.ResolveReleaseMediaAsset(releaseAssets, runtimemedia.MediaDeliveryBases{Avatar: mediaAvatarBaseURL}, profile.AvatarAsset.AssetID, profile.AvatarAsset.Kind, profile.AvatarAsset.SHA256, "creators/"+ref)
			if resolveErr != nil {
				return desiredState{}, nil, fmt.Errorf("creator %s avatar differs from release media authority: %w", ref, resolveErr)
			}
			profile.AvatarURL, profile.AvatarVersion, profile.AvatarPublicSliceKey = resolved.DeliveryRef, resolved.Version, resolved.PublicSliceKey
		}
		works, err := loadCreatorWorks(filepath.Join(root, "works.refs.ndjson"))
		if err != nil {
			return desiredState{}, nil, err
		}
		records = append(records, creatorRecord{Profile: profile, ProfileDigest: profileDigest, Works: works})
	}
	sort.Slice(records, func(left, right int) bool { return records[left].Profile.CreatorID < records[right].Profile.CreatorID })
	return state, records, nil
}

func buildCandidate(identity model.ReleaseIdentity, creators []creatorRecord, verifiedAt time.Time) ([]model.CreatorReleaseProjection, model.CreatorReleaseCandidateState, error) {
	projections := make([]model.CreatorReleaseProjection, 0, len(creators))
	authors := make([]string, 0, len(creators))
	profileDigests := make([]model.CreatorProfileDigestBinding, 0, len(creators))
	parts := make([]string, 0, len(creators))
	for _, creator := range creators {
		profile := creator.Profile
		runtime := model.CreatorRuntimeProfile{CreatorID: profile.CreatorID, PersonaID: profile.PersonaID, Handle: profile.UserHandle, DisplayName: profile.DisplayName, Headline: profile.Headline, Bio: profile.Bio, AvatarURL: profile.AvatarURL, AvatarVersion: profile.AvatarVersion, AvatarPublicSliceKey: profile.AvatarPublicSliceKey, PublicProfileTagRefs: append([]string(nil), profile.PublicProfileTagRefs...), CreatorArchetype: profile.CreatorArchetype, Disclosure: profile.Disclosure, Works: append([]model.CreatorWorkRef(nil), creator.Works...), PackageDigest: identity.ManifestDigest, ReleaseID: identity.ReleaseID, Status: "candidate", ManagedBy: identity.SourceOwner, ImportedAt: verifiedAt, UpdatedAt: verifiedAt}
		if profile.AvatarAsset != nil {
			runtime.AvatarAssetID, runtime.AvatarSHA256 = profile.AvatarAsset.AssetID, profile.AvatarAsset.SHA256
		}
		projection := model.CreatorReleaseProjection{ReleaseIdentity: identity, CreatorID: profile.CreatorID, PersonaID: profile.PersonaID, Profile: runtime, AuthorID: profile.AuthorID, ProfileDigest: creator.ProfileDigest, ProjectionVersion: projectionVersion, VerifiedAt: verifiedAt}
		digest, err := creatorpersistence.DocumentDigest(projection, "documentDigest")
		if err != nil {
			return nil, model.CreatorReleaseCandidateState{}, err
		}
		projection.DocumentDigest = digest
		projections = append(projections, projection)
		authors = append(authors, profile.AuthorID)
		profileDigests = append(profileDigests, model.CreatorProfileDigestBinding{CreatorID: profile.CreatorID, AuthorID: profile.AuthorID, Digest: creator.ProfileDigest})
		parts = append(parts, profile.CreatorID+"="+digest)
	}
	sort.Strings(authors)
	sort.Slice(profileDigests, func(left, right int) bool { return profileDigests[left].CreatorID < profileDigests[right].CreatorID })
	candidate := model.CreatorReleaseCandidateState{ReleaseIdentity: identity, Status: "verified", ProjectionVersion: projectionVersion, VerifiedAt: verifiedAt, ClosureDigest: creatorpersistence.ClosureDigest(parts), ExpectedCount: len(creators), ProjectedCount: len(creators), AuthorIDs: authors, ProfileDigests: profileDigests}
	return projections, candidate, nil
}

func candidateImportReport(candidate model.CreatorReleaseCandidateState, verifiedCreatorIDs []string, dryRun bool, generatedAt time.Time) importReport {
	status := "verified"
	var verifiedAt *time.Time
	projection := candidate.ProjectionVersion
	closure := candidate.ClosureDigest
	projected := candidate.ProjectedCount
	if dryRun {
		status, projection, closure, projected = "dry-run", 0, "", 0
	} else {
		value := candidate.VerifiedAt.UTC()
		verifiedAt = &value
	}
	return importReport{Schema: reportSchema, Status: status, Environment: candidate.Environment, ReleaseID: candidate.ReleaseID, SourceOwner: candidate.SourceOwner, ManifestDigest: candidate.ManifestDigest, ActivationMode: activationStageOnly, ProjectionDatabase: projectionDatabase, ProjectionVersion: projection, ClosureDigest: closure, VerifiedAt: verifiedAt, Counts: counts{CreatorsExpected: candidate.ExpectedCount, CreatorsProjected: projected}, AuthorIDs: append([]string(nil), candidate.AuthorIDs...), ProfileDigests: append([]model.CreatorProfileDigestBinding(nil), candidate.ProfileDigests...), VerifiedCreatorIDs: verifiedCreatorIDs, PostgreSQLWrites: candidate.PostgreSQLWrites, GeneratedAt: generatedAt.Format(time.RFC3339Nano)}
}

func loadReleaseClass(releaseRoot string) (string, error) {
	raw, err := os.ReadFile(filepath.Join(releaseRoot, "payload", "release.json"))
	if err != nil {
		return "", fmt.Errorf("read release header: %w", err)
	}
	var header struct {
		ReleaseClass string `json:"releaseClass"`
	}
	if err := json.Unmarshal(raw, &header); err != nil {
		return "", fmt.Errorf("decode release header: %w", err)
	}
	if strings.TrimSpace(header.ReleaseClass) == "" {
		return "", fmt.Errorf("release header releaseClass is required")
	}
	return strings.TrimSpace(header.ReleaseClass), nil
}

func safeRef(ref string) error {
	clean := filepath.Clean(filepath.FromSlash(strings.TrimSpace(ref)))
	if ref == "" || filepath.IsAbs(clean) || clean == "." || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return fmt.Errorf("unsafe creator desired ref: %q", ref)
	}
	return nil
}

func loadCreatorProfile(root, ref string) (creatorProfile, string, error) {
	path := filepath.Join(root, "profile.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		return creatorProfile{}, "", fmt.Errorf("read creator profile %s: %w", ref, err)
	}
	var profile creatorProfile
	if err := json.Unmarshal(raw, &profile); err != nil {
		return creatorProfile{}, "", fmt.Errorf("decode creator profile %s: %w", ref, err)
	}
	if strings.TrimSpace(profile.AvatarObjectKey) != "" || (profile.AvatarAsset != nil && strings.TrimSpace(profile.AvatarAsset.ObjectKey) != "") {
		return creatorProfile{}, "", fmt.Errorf("creator profile %s contains forbidden avatar objectKey", ref)
	}
	if profile.Schema != "quwoquan_data.creator_profile" || profile.CreatorID != ref || profile.UserID == "" || profile.AuthorID == "" || profile.UserID != profile.AuthorID || profile.PersonaID == "" || profile.DisplayName == "" {
		return creatorProfile{}, "", fmt.Errorf("invalid creator profile: %s", ref)
	}
	return profile, digestCanonicalJSON(raw), nil
}

func loadCreatorWorks(path string) ([]model.CreatorWorkRef, error) {
	file, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return []model.CreatorWorkRef{}, nil
		}
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

func digestCanonicalJSON(raw []byte) string {
	var value any
	if err := json.Unmarshal(raw, &value); err != nil {
		return ""
	}
	canonical, err := json.Marshal(value)
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(canonical)
	return "sha256:" + hex.EncodeToString(sum[:])
}
func creatorIDs(creators []creatorRecord) []string {
	ids := make([]string, 0, len(creators))
	for _, creator := range creators {
		ids = append(ids, creator.Profile.CreatorID)
	}
	sort.Strings(ids)
	return ids
}
func fatal(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, "release creator import:", err)
		os.Exit(1)
	}
}
