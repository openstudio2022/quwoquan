package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"regexp"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

const (
	creatorReleaseProjectionCollection = "creator_release_projections"
	creatorReleaseStateCollection      = "creator_release_candidate_states"
)

var creatorReleaseDigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// CreatorReleaseCandidateStore persists and verifies owner-local immutable
// candidates. It deliberately has no activation/latest operation.
type CreatorReleaseCandidateStore struct {
	projections *mongo.Collection
	states      *mongo.Collection
}

func NewCreatorReleaseCandidateStore(database *mongo.Database) *CreatorReleaseCandidateStore {
	if database == nil {
		return &CreatorReleaseCandidateStore{}
	}
	return &CreatorReleaseCandidateStore{
		projections: database.Collection(creatorReleaseProjectionCollection),
		states:      database.Collection(creatorReleaseStateCollection),
	}
}

func (s *CreatorReleaseCandidateStore) EnsureIndexes(ctx context.Context) error {
	if s == nil || s.projections == nil || s.states == nil {
		return fmt.Errorf("Creator release candidate store is unavailable")
	}
	_, err := s.projections.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "creatorId", Value: 1}}, Options: options.Index().SetName("uq_creator_release_projection_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "personaId", Value: 1}}, Options: options.Index().SetName("idx_creator_release_projection_public_identity")},
	})
	if err != nil {
		return fmt.Errorf("ensure Creator release projection indexes: %w", err)
	}
	_, err = s.states.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}},
		Options: options.Index().SetName("uq_creator_release_candidate_identity").SetUnique(true),
	})
	if err != nil {
		return fmt.Errorf("ensure Creator release state index: %w", err)
	}
	return nil
}

// Stage inserts one create-once candidate or verifies an exact replay. Mongo
// transaction keeps projections and their verified state inseparable.
func (s *CreatorReleaseCandidateStore) Stage(ctx context.Context, state model.CreatorReleaseCandidateState, projections []model.CreatorReleaseProjection) (bool, error) {
	if s == nil || s.projections == nil || s.states == nil {
		return false, fmt.Errorf("Creator release candidate store is unavailable")
	}
	if err := validateCandidateInput(state, projections); err != nil {
		return false, err
	}
	filter := releaseIdentityFilter(state.ReleaseIdentity)
	var current model.CreatorReleaseCandidateState
	err := s.states.FindOne(ctx, filter).Decode(&current)
	if err == nil {
		if err := s.validateExactReplay(ctx, state, projections, current); err != nil {
			return false, err
		}
		return true, nil
	}
	if err != mongo.ErrNoDocuments {
		return false, fmt.Errorf("read exact Creator release candidate: %w", err)
	}
	session, err := s.projections.Database().Client().StartSession()
	if err != nil {
		return false, err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var existing model.CreatorReleaseCandidateState
		readErr := s.states.FindOne(txCtx, filter).Decode(&existing)
		if readErr == nil {
			return nil, fmt.Errorf("Creator release candidate already exists")
		}
		if readErr != mongo.ErrNoDocuments {
			return nil, readErr
		}
		if len(projections) > 0 {
			documents := make([]any, 0, len(projections))
			for _, projection := range projections {
				documents = append(documents, projection)
			}
			if _, insertErr := s.projections.InsertMany(txCtx, documents); insertErr != nil {
				return nil, insertErr
			}
		}
		if verifyErr := s.validateStoredCandidate(txCtx, state, state); verifyErr != nil {
			return nil, verifyErr
		}
		if verifyErr := s.validateStoredCandidate(txCtx, state, state); verifyErr != nil {
			return nil, verifyErr
		}
		_, insertErr := s.states.InsertOne(txCtx, state)
		return nil, insertErr
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) || strings.Contains(err.Error(), "already exists") {
			if readErr := s.states.FindOne(ctx, filter).Decode(&current); readErr != nil {
				return false, err
			}
			if readErr := s.validateExactReplay(ctx, state, projections, current); readErr != nil {
				return false, readErr
			}
			return true, nil
		}
		return false, fmt.Errorf("stage Creator release candidate: %w", err)
	}
	return false, nil
}

// ReadVerifiedCandidate reads one exact identity and revalidates its real
// storage closure. Absence is not an error and never falls back to latest.
func (s *CreatorReleaseCandidateStore) ReadVerifiedCandidate(ctx context.Context, identity model.ReleaseIdentity) (model.CreatorReleaseCandidateState, bool, error) {
	if s == nil || s.projections == nil || s.states == nil {
		return model.CreatorReleaseCandidateState{}, false, fmt.Errorf("Creator release candidate store is unavailable")
	}
	if err := validateReleaseIdentity(identity); err != nil {
		return model.CreatorReleaseCandidateState{}, false, err
	}
	var state model.CreatorReleaseCandidateState
	err := s.states.FindOne(ctx, releaseIdentityFilter(identity)).Decode(&state)
	if err == mongo.ErrNoDocuments {
		return model.CreatorReleaseCandidateState{ReleaseIdentity: identity}, false, nil
	}
	if err != nil {
		return model.CreatorReleaseCandidateState{}, false, fmt.Errorf("read exact verified Creator release candidate: %w", err)
	}
	if err := s.validateStoredCandidate(ctx, state, state); err != nil {
		return model.CreatorReleaseCandidateState{}, false, err
	}
	return state, true, nil
}

// FindByExactContentFence is the public-reader seam. Content supplies the
// authoritative live tuple; this method performs no pointer/latest lookup.
func (s *CreatorReleaseCandidateStore) FindByExactContentFence(ctx context.Context, identity model.ReleaseIdentity, publicIdentity string) (*model.CreatorRuntimeProfile, bool, error) {
	state, found, err := s.ReadVerifiedCandidate(ctx, identity)
	if err != nil || !found {
		return nil, false, err
	}
	publicIdentity = strings.TrimSpace(publicIdentity)
	if publicIdentity == "" {
		return nil, false, nil
	}
	filter := releaseIdentityFilter(identity)
	filter["$or"] = bson.A{bson.M{"creatorId": publicIdentity}, bson.M{"personaId": publicIdentity}}
	cursor, err := s.projections.Find(ctx, filter, options.Find().SetLimit(2))
	if err != nil {
		return nil, false, err
	}
	defer cursor.Close(ctx)
	var documents []model.CreatorReleaseProjection
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, false, err
	}
	if len(documents) > 1 {
		return nil, false, fmt.Errorf("Creator public identity %q is not unique inside exact Content fence", publicIdentity)
	}
	if len(documents) == 0 {
		return nil, false, nil
	}
	document := documents[0]
	if document.ProjectionVersion != state.ProjectionVersion || !document.VerifiedAt.Equal(state.VerifiedAt) {
		return nil, false, fmt.Errorf("GATE_BLOCK: Creator projection verification binding drift")
	}
	actual, err := DocumentDigest(document, "documentDigest")
	if err != nil || actual != document.DocumentDigest {
		return nil, false, fmt.Errorf("GATE_BLOCK: Creator projection document digest drift")
	}
	profile := document.Profile
	return &profile, true, nil
}

// validateExactReplay admits a second Stage of the same tuple only when the
// immutable intent and the timestamp-free projection payload equal what is
// stored. verifiedAt and the closure digest derived from it belong to the
// stored attestation, so they are validated against storage rather than
// against the replaying run's own clock.
func (s *CreatorReleaseCandidateStore) validateExactReplay(ctx context.Context, requested model.CreatorReleaseCandidateState, projections []model.CreatorReleaseProjection, stored model.CreatorReleaseCandidateState) error {
	if !sameCandidateIntent(requested, stored) {
		return fmt.Errorf("GATE_BLOCK: Creator release candidate state drift for exact tuple")
	}
	if err := s.validateStoredCandidate(ctx, stored, stored); err != nil {
		return err
	}
	cursor, err := s.projections.Find(ctx, releaseIdentityFilter(stored.ReleaseIdentity), options.Find().SetSort(bson.D{{Key: "creatorId", Value: 1}}))
	if err != nil {
		return err
	}
	defer cursor.Close(ctx)
	storedPayloads := make(map[string]string, stored.ProjectedCount)
	for cursor.Next(ctx) {
		var document model.CreatorReleaseProjection
		if err := cursor.Decode(&document); err != nil {
			return err
		}
		digest, err := replayPayloadDigest(document)
		if err != nil {
			return err
		}
		storedPayloads[document.CreatorID] = digest
	}
	if err := cursor.Err(); err != nil {
		return err
	}
	if len(storedPayloads) != len(projections) {
		return fmt.Errorf("GATE_BLOCK: Creator release candidate payload drift for exact tuple")
	}
	for _, projection := range projections {
		digest, err := replayPayloadDigest(projection)
		if err != nil {
			return err
		}
		if storedPayloads[projection.CreatorID] != digest {
			return fmt.Errorf("GATE_BLOCK: Creator release candidate payload drift for exact tuple")
		}
	}
	return nil
}

// replayPayloadDigest hashes one projection with its verification clock and
// derived document digest cleared, so two stagings of the same immutable
// payload compare equal regardless of when they ran.
func replayPayloadDigest(projection model.CreatorReleaseProjection) (string, error) {
	projection.VerifiedAt = time.Time{}
	projection.Profile.ImportedAt = time.Time{}
	projection.Profile.UpdatedAt = time.Time{}
	projection.DocumentDigest = ""
	return DocumentDigest(projection, "documentDigest")
}

func (s *CreatorReleaseCandidateStore) validateStoredCandidate(ctx context.Context, expected, actual model.CreatorReleaseCandidateState) error {
	if !sameCandidateState(expected, actual) {
		return fmt.Errorf("GATE_BLOCK: Creator release candidate state drift for exact tuple")
	}
	cursor, err := s.projections.Find(ctx, releaseIdentityFilter(actual.ReleaseIdentity), options.Find().SetSort(bson.D{{Key: "creatorId", Value: 1}}))
	if err != nil {
		return err
	}
	defer cursor.Close(ctx)
	count := 0
	parts := make([]string, 0, actual.ProjectedCount)
	authorIDs := make([]string, 0, actual.ProjectedCount)
	profileDigests := make([]model.CreatorProfileDigestBinding, 0, actual.ProjectedCount)
	for cursor.Next(ctx) {
		var document model.CreatorReleaseProjection
		if err := cursor.Decode(&document); err != nil {
			return err
		}
		computed, err := DocumentDigest(document, "documentDigest")
		if err != nil || computed != document.DocumentDigest || !creatorReleaseDigestPattern.MatchString(document.ProfileDigest) {
			return fmt.Errorf("GATE_BLOCK: Creator candidate document digest drift: stored=%q computed=%q err=%v", document.DocumentDigest, computed, err)
		}
		if document.ReleaseIdentity != actual.ReleaseIdentity || document.ProjectionVersion != actual.ProjectionVersion || !document.VerifiedAt.Equal(actual.VerifiedAt) {
			return fmt.Errorf("GATE_BLOCK: Creator candidate document identity drift")
		}
		parts = append(parts, document.CreatorID+"="+document.DocumentDigest)
		authorIDs = append(authorIDs, document.AuthorID)
		profileDigests = append(profileDigests, model.CreatorProfileDigestBinding{CreatorID: document.CreatorID, AuthorID: document.AuthorID, Digest: document.ProfileDigest})
		count++
	}
	if err := cursor.Err(); err != nil {
		return err
	}
	sort.Strings(authorIDs)
	sort.Slice(profileDigests, func(left, right int) bool { return profileDigests[left].CreatorID < profileDigests[right].CreatorID })
	if count != actual.ExpectedCount || count != actual.ProjectedCount || !equalStrings(authorIDs, actual.AuthorIDs) || !equalProfileDigests(profileDigests, actual.ProfileDigests) {
		return fmt.Errorf("GATE_BLOCK: Creator candidate closure count or identity drift")
	}
	if ClosureDigest(parts) != actual.ClosureDigest {
		return fmt.Errorf("GATE_BLOCK: Creator candidate closure digest drift")
	}
	return nil
}

func validateCandidateInput(state model.CreatorReleaseCandidateState, projections []model.CreatorReleaseProjection) error {
	if err := validateReleaseIdentity(state.ReleaseIdentity); err != nil {
		return err
	}
	if state.Status != "verified" || state.ProjectionVersion <= 0 || state.VerifiedAt.IsZero() || !creatorReleaseDigestPattern.MatchString(state.ClosureDigest) || state.ExpectedCount < 0 || state.ProjectedCount != state.ExpectedCount || len(projections) != state.ProjectedCount {
		return fmt.Errorf("Creator release candidate verification is incomplete")
	}
	if state.PostgreSQLWrites != (model.CandidatePostgreSQLWriteCounts{}) {
		return fmt.Errorf("Creator release candidate must attest zero PostgreSQL User/Persona writes")
	}
	if !strictlySortedStrings(state.AuthorIDs) || !sort.SliceIsSorted(state.ProfileDigests, func(left, right int) bool {
		return state.ProfileDigests[left].CreatorID < state.ProfileDigests[right].CreatorID
	}) {
		return fmt.Errorf("Creator release candidate identity arrays must be sorted and unique")
	}
	for index, binding := range state.ProfileDigests {
		if strings.TrimSpace(binding.CreatorID) == "" || strings.TrimSpace(binding.AuthorID) == "" || !creatorReleaseDigestPattern.MatchString(binding.Digest) || (index > 0 && state.ProfileDigests[index-1].CreatorID == binding.CreatorID) {
			return fmt.Errorf("Creator release candidate profile digest binding is invalid")
		}
	}
	parts := make([]string, 0, len(projections))
	authorIDs := make([]string, 0, len(projections))
	profileDigests := make([]model.CreatorProfileDigestBinding, 0, len(projections))
	for _, projection := range projections {
		if projection.ReleaseIdentity != state.ReleaseIdentity || projection.ProjectionVersion != state.ProjectionVersion || !projection.VerifiedAt.Equal(state.VerifiedAt) || strings.TrimSpace(projection.CreatorID) == "" || projection.CreatorID != projection.Profile.CreatorID || strings.TrimSpace(projection.AuthorID) == "" || strings.TrimSpace(projection.PersonaID) == "" || projection.PersonaID != projection.Profile.PersonaID || !creatorReleaseDigestPattern.MatchString(projection.ProfileDigest) || !creatorReleaseDigestPattern.MatchString(projection.DocumentDigest) {
			return fmt.Errorf("Creator release projection is incomplete")
		}
		computed, err := DocumentDigest(projection, "documentDigest")
		if err != nil || computed != projection.DocumentDigest {
			return fmt.Errorf("Creator release projection document digest is invalid")
		}
		parts = append(parts, projection.CreatorID+"="+projection.DocumentDigest)
		authorIDs = append(authorIDs, projection.AuthorID)
		profileDigests = append(profileDigests, model.CreatorProfileDigestBinding{CreatorID: projection.CreatorID, AuthorID: projection.AuthorID, Digest: projection.ProfileDigest})
	}
	sort.Strings(authorIDs)
	sort.Slice(profileDigests, func(left, right int) bool { return profileDigests[left].CreatorID < profileDigests[right].CreatorID })
	if ClosureDigest(parts) != state.ClosureDigest || !equalStrings(authorIDs, state.AuthorIDs) || !equalProfileDigests(profileDigests, state.ProfileDigests) {
		return fmt.Errorf("Creator release candidate input closure is inconsistent")
	}
	return nil
}

func validateReleaseIdentity(identity model.ReleaseIdentity) error {
	if strings.TrimSpace(identity.Environment) == "" || identity.SourceOwner != "qwq_data" || strings.TrimSpace(identity.ReleaseID) == "" || !creatorReleaseDigestPattern.MatchString(identity.ManifestDigest) {
		return fmt.Errorf("Creator release identity is incomplete or non-canonical")
	}
	return nil
}

func releaseIdentityFilter(identity model.ReleaseIdentity) bson.M {
	return bson.M{"environment": identity.Environment, "sourceOwner": identity.SourceOwner, "releaseId": identity.ReleaseID, "manifestDigest": identity.ManifestDigest}
}

// sameCandidateIntent compares the timestamp-independent immutable intent of
// a candidate; verifiedAt and closureDigest are attested per staging run.
func sameCandidateIntent(left, right model.CreatorReleaseCandidateState) bool {
	return left.ReleaseIdentity == right.ReleaseIdentity && left.Status == right.Status && left.ProjectionVersion == right.ProjectionVersion && left.ExpectedCount == right.ExpectedCount && left.ProjectedCount == right.ProjectedCount && left.PostgreSQLWrites == right.PostgreSQLWrites && equalStrings(left.AuthorIDs, right.AuthorIDs) && equalProfileDigests(left.ProfileDigests, right.ProfileDigests)
}

func sameCandidateState(left, right model.CreatorReleaseCandidateState) bool {
	return left.ReleaseIdentity == right.ReleaseIdentity && left.Status == right.Status && left.ProjectionVersion == right.ProjectionVersion && left.VerifiedAt.Equal(right.VerifiedAt) && left.ClosureDigest == right.ClosureDigest && left.ExpectedCount == right.ExpectedCount && left.ProjectedCount == right.ProjectedCount && left.PostgreSQLWrites == right.PostgreSQLWrites && equalStrings(left.AuthorIDs, right.AuthorIDs) && equalProfileDigests(left.ProfileDigests, right.ProfileDigests)
}

func strictlySortedStrings(values []string) bool {
	for index, value := range values {
		if strings.TrimSpace(value) == "" || (index > 0 && values[index-1] >= value) {
			return false
		}
	}
	return true
}

func equalProfileDigests(left, right []model.CreatorProfileDigestBinding) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func equalStrings(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

// DocumentDigest hashes canonical Extended JSON after removing named fields.
func DocumentDigest(document any, excludedFields ...string) (string, error) {
	raw, err := bson.Marshal(document)
	if err != nil {
		return "", err
	}
	var normalized bson.M
	if err := bson.Unmarshal(raw, &normalized); err != nil {
		return "", err
	}
	delete(normalized, "_id")
	for _, field := range excludedFields {
		delete(normalized, field)
	}
	extended, err := bson.MarshalExtJSON(normalized, true, false)
	if err != nil {
		return "", err
	}
	var value any
	if err := json.Unmarshal(extended, &value); err != nil {
		return "", err
	}
	canonical, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(canonical)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

// ClosureDigest binds sorted creatorId=documentDigest rows.
func ClosureDigest(parts []string) string {
	parts = append([]string(nil), parts...)
	sort.Strings(parts)
	sum := sha256.Sum256([]byte(strings.Join(parts, "\n")))
	return "sha256:" + hex.EncodeToString(sum[:])
}
