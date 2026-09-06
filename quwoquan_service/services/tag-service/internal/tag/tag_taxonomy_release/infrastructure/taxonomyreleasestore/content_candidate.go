// Package taxonomyreleasestore owns the Tag projection of Data content-release
// candidates. Candidates stop at verified and never act as a Tag active pointer.
package taxonomyreleasestore

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/lifecycle"
	nodemodel "quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

const (
	ContentCandidateCollection              = "tag_release_candidates"
	ContentCandidateIdentityIndex           = "uq_tag_release_candidate_identity"
	ContentCandidateReleaseFenceIndex       = "uq_tag_release_candidate_release_fence"
	TagNodeReleaseTagRefIndex               = "uq_tag_nodes_release_tag_ref"
	TagNodeReleaseLifecycleIndex            = "idx_tag_nodes_release_lifecycle_group_depth_tagref"
	TagNodeReleaseParentIndex               = "idx_tag_nodes_release_parent_lifecycle_tagref"
	TagNodeReleaseKindIndex                 = "idx_tag_nodes_release_kind_group_tagref"
	TagCandidateProjectionVersion     int64 = 1
)

var sha256DigestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type ContentCandidate struct {
	Environment        string    `bson:"environment" json:"environment"`
	SourceOwner        string    `bson:"sourceOwner" json:"sourceOwner"`
	ReleaseID          string    `bson:"releaseId" json:"releaseId"`
	ManifestDigest     string    `bson:"manifestDigest" json:"manifestDigest"`
	Status             string    `bson:"status" json:"status"`
	ProjectionVersion  int64     `bson:"projectionVersion" json:"projectionVersion"`
	VerifiedAt         time.Time `bson:"verifiedAt" json:"verifiedAt"`
	ClosureDigest      string    `bson:"closureDigest" json:"closureDigest"`
	ExpectedNodeCount  int       `bson:"expectedNodeCount" json:"expectedNodeCount"`
	ProjectedNodeCount int       `bson:"projectedNodeCount" json:"projectedNodeCount"`
	CanonicalDigest    string    `bson:"canonicalDigest" json:"canonicalDigest"`
	ReleaseKind        string    `bson:"releaseKind" json:"releaseKind"`
	TagRefsDigest      string    `bson:"tagRefsDigest" json:"tagRefsDigest"`
}

type ContentCandidateStore struct {
	candidates *mongo.Collection
	nodes      *mongo.Collection
}

func NewContentCandidateStore(database *mongo.Database) *ContentCandidateStore {
	if database == nil {
		return &ContentCandidateStore{}
	}
	return &ContentCandidateStore{
		candidates: database.Collection(ContentCandidateCollection),
		nodes:      database.Collection("tag_nodes"),
	}
}

func (s *ContentCandidateStore) EnsureIndexes(ctx context.Context) error {
	if s.candidates == nil || s.nodes == nil {
		return errors.New("tag content candidate database is required")
	}
	_, err := s.candidates.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1},
			},
			Options: options.Index().SetName(ContentCandidateIdentityIndex).SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1},
			},
			Options: options.Index().SetName(ContentCandidateReleaseFenceIndex).SetUnique(true),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure Tag content candidate indexes: %w", err)
	}
	return nil
}

// StageVerified inserts one immutable verified candidate. A duplicate exact
// candidate is accepted only after a full closure readback. A different
// manifest for the same environment/owner/release fence conflicts at storage.
func (s *ContentCandidateStore) StageVerified(ctx context.Context, requested ContentCandidate) (ContentCandidate, bool, error) {
	if err := validateContentCandidate(requested); err != nil {
		return ContentCandidate{}, false, err
	}
	if err := s.inspectQueryIndexes(ctx); err != nil {
		return ContentCandidate{}, false, err
	}
	if err := s.validateStoredCandidate(ctx, requested); err != nil {
		return ContentCandidate{}, false, err
	}
	_, err := s.candidates.InsertOne(ctx, requested)
	if err == nil {
		return requested, false, nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return ContentCandidate{}, false, fmt.Errorf("insert verified Tag content candidate: %w", err)
	}
	existing, found, loadErr := s.loadExact(ctx, requested.Environment, requested.SourceOwner, requested.ReleaseID, requested.ManifestDigest)
	if loadErr != nil {
		return ContentCandidate{}, false, loadErr
	}
	if !found {
		return ContentCandidate{}, false, fmt.Errorf("tag content release candidate fence conflicts with another manifest")
	}
	if !sameContentCandidate(existing, requested) {
		return ContentCandidate{}, false, fmt.Errorf("tag content release candidate immutable intent drift")
	}
	if err := s.validateStoredCandidate(ctx, existing); err != nil {
		return ContentCandidate{}, false, err
	}
	return existing, true, nil
}

// ReadVerifiedContentCandidate is the exact owner query seam. It never scans
// latest and performs no index creation or other mutation.
func (s *ContentCandidateStore) ReadVerifiedContentCandidate(
	ctx context.Context,
	environment, sourceOwner, releaseID, manifestDigest string,
) (ContentCandidate, bool, error) {
	environment = strings.TrimSpace(environment)
	sourceOwner = strings.TrimSpace(sourceOwner)
	releaseID = strings.TrimSpace(releaseID)
	manifestDigest = strings.TrimSpace(manifestDigest)
	if environment == "" || sourceOwner != "qwq_data" || releaseID == "" ||
		!sha256DigestPattern.MatchString(manifestDigest) {
		return ContentCandidate{}, false, errors.New("exact Tag candidate query binding is invalid")
	}
	if err := s.inspectQueryIndexes(ctx); err != nil {
		return ContentCandidate{}, false, err
	}
	candidate, found, err := s.loadExact(ctx, environment, sourceOwner, releaseID, manifestDigest)
	if err != nil || !found {
		return candidate, found, err
	}
	if err := s.validateStoredCandidate(ctx, candidate); err != nil {
		return ContentCandidate{}, false, err
	}
	return candidate, true, nil
}

func (s *ContentCandidateStore) loadExact(
	ctx context.Context,
	environment, sourceOwner, releaseID, manifestDigest string,
) (ContentCandidate, bool, error) {
	var candidate ContentCandidate
	err := s.candidates.FindOne(ctx, bson.M{
		"environment": environment, "sourceOwner": sourceOwner,
		"releaseId": releaseID, "manifestDigest": manifestDigest,
	}).Decode(&candidate)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ContentCandidate{
			Environment: environment, SourceOwner: sourceOwner,
			ReleaseID: releaseID, ManifestDigest: manifestDigest,
		}, false, nil
	}
	if err != nil {
		return ContentCandidate{}, false, fmt.Errorf("read exact Tag content candidate: %w", err)
	}
	return candidate, true, nil
}

func (s *ContentCandidateStore) validateStoredCandidate(ctx context.Context, candidate ContentCandidate) error {
	if err := validateContentCandidate(candidate); err != nil {
		return fmt.Errorf("GATE_BLOCK: persisted Tag candidate is invalid: %w", err)
	}
	nodes, err := s.readCanonicalNodes(ctx, candidate.ReleaseID)
	if err != nil {
		return err
	}
	if len(nodes) != candidate.ExpectedNodeCount || len(nodes) != candidate.ProjectedNodeCount {
		return fmt.Errorf("GATE_BLOCK: Tag candidate node count drift: expected=%d projected=%d actual=%d", candidate.ExpectedNodeCount, candidate.ProjectedNodeCount, len(nodes))
	}
	if digestTagRefs(nodes) != candidate.TagRefsDigest {
		return errors.New("GATE_BLOCK: Tag candidate tagRefs digest drift")
	}
	canonical, err := digestCanonicalNodes(nodes)
	if err != nil {
		return err
	}
	if canonical != candidate.CanonicalDigest {
		return errors.New("GATE_BLOCK: Tag candidate canonical digest drift")
	}
	closure, err := digestNodeClosure(nodes)
	if err != nil {
		return err
	}
	if closure != candidate.ClosureDigest {
		return errors.New("GATE_BLOCK: Tag candidate node closure digest drift")
	}
	return nil
}

func (s *ContentCandidateStore) readCanonicalNodes(ctx context.Context, releaseID string) ([]nodemodel.TagNode, error) {
	cursor, err := s.nodes.Find(ctx, bson.M{"releaseId": releaseID}, options.Find().SetSort(bson.D{{Key: "tagRef", Value: 1}}))
	if err != nil {
		return nil, fmt.Errorf("read Tag candidate nodes: %w", err)
	}
	defer cursor.Close(ctx)
	var nodes []nodemodel.TagNode
	if err := cursor.All(ctx, &nodes); err != nil {
		return nil, fmt.Errorf("decode Tag candidate nodes: %w", err)
	}
	for index := range nodes {
		if strings.TrimSpace(nodes[index].ReleaseID) != releaseID || strings.TrimSpace(nodes[index].TagRef) == "" {
			return nil, errors.New("GATE_BLOCK: Tag candidate node identity is invalid")
		}
		if index > 0 && nodes[index-1].TagRef == nodes[index].TagRef {
			return nil, errors.New("GATE_BLOCK: Tag candidate contains duplicate tagRef")
		}
	}
	return nodes, nil
}

func validateContentCandidate(candidate ContentCandidate) error {
	environment := strings.TrimSpace(candidate.Environment)
	sourceOwner := strings.TrimSpace(candidate.SourceOwner)
	releaseID := strings.TrimSpace(candidate.ReleaseID)
	manifestDigest := strings.TrimSpace(candidate.ManifestDigest)
	if candidate.Environment != environment || candidate.SourceOwner != sourceOwner ||
		candidate.ReleaseID != releaseID || candidate.ManifestDigest != manifestDigest ||
		environment == "" || sourceOwner != "qwq_data" ||
		candidate.ReleaseID == "" || !sha256DigestPattern.MatchString(candidate.ManifestDigest) {
		return errors.New("Tag content candidate identity is invalid")
	}
	if candidate.Status != "verified" || candidate.ProjectionVersion <= 0 || candidate.VerifiedAt.IsZero() {
		return errors.New("Tag content candidate is not verified")
	}
	if candidate.ExpectedNodeCount < 0 || candidate.ProjectedNodeCount != candidate.ExpectedNodeCount {
		return errors.New("Tag content candidate counts are invalid")
	}
	if candidate.ReleaseKind != "content" && candidate.ReleaseKind != "empty_baseline" {
		return errors.New("Tag content candidate releaseKind is invalid")
	}
	if (candidate.ReleaseKind == "content" && candidate.ExpectedNodeCount == 0) ||
		(candidate.ReleaseKind == "empty_baseline" && candidate.ExpectedNodeCount != 0) {
		return errors.New("Tag content candidate releaseKind/count binding is invalid")
	}
	for label, digest := range map[string]string{
		"canonicalDigest": candidate.CanonicalDigest,
		"closureDigest":   candidate.ClosureDigest,
		"tagRefsDigest":   candidate.TagRefsDigest,
	} {
		if !sha256DigestPattern.MatchString(digest) {
			return fmt.Errorf("Tag content candidate %s is invalid", label)
		}
	}
	return nil
}

func sameContentCandidate(left, right ContentCandidate) bool {
	return left.Environment == right.Environment && left.SourceOwner == right.SourceOwner &&
		left.ReleaseID == right.ReleaseID && left.ManifestDigest == right.ManifestDigest &&
		left.Status == right.Status && left.ProjectionVersion == right.ProjectionVersion &&
		left.ClosureDigest == right.ClosureDigest &&
		left.ExpectedNodeCount == right.ExpectedNodeCount && left.ProjectedNodeCount == right.ProjectedNodeCount &&
		left.CanonicalDigest == right.CanonicalDigest && left.ReleaseKind == right.ReleaseKind &&
		left.TagRefsDigest == right.TagRefsDigest
}

func digestTagRefs(nodes []nodemodel.TagNode) string {
	refs := make([]string, 0, len(nodes))
	for _, node := range nodes {
		refs = append(refs, node.TagRef)
	}
	return sha256Text(strings.Join(refs, "\n"))
}

func digestCanonicalNodes(nodes []nodemodel.TagNode) (string, error) {
	hasher := sha256.New()
	for _, node := range nodes {
		fmt.Fprintf(hasher, "%s\x00%s\x00%s\x00%s\x00%s\x00%s\x00%s\x00%d\x00%d\x00%s\x00%s\x00%s\x00%s\x00%s\x00%s\n",
			node.TagRef, node.Group, node.NodeKind, node.Label, node.LabelEn, node.Description,
			node.ParentTagRef, node.Depth, node.MaxDepth, node.PathPolicy,
			strings.Join(node.Aliases, "\x1f"), node.AxisRole, strings.Join(node.SameAsRefs, "\x1f"),
			node.LifecycleStatus, lifecycle.CanonicalWindow(node.HeatWindow))
	}
	return "sha256:" + hex.EncodeToString(hasher.Sum(nil)), nil
}

func digestNodeClosure(nodes []nodemodel.TagNode) (string, error) {
	rows := make([]string, 0, len(nodes))
	for _, node := range nodes {
		copy := node
		copy.CreatedAt = time.Time{}
		copy.UpdatedAt = time.Time{}
		encoded, err := json.Marshal(copy)
		if err != nil {
			return "", fmt.Errorf("encode Tag candidate node closure: %w", err)
		}
		rows = append(rows, node.TagRef+"="+sha256Bytes(encoded))
	}
	return sha256Text(strings.Join(rows, "\n")), nil
}

func sha256Text(value string) string { return sha256Bytes([]byte(value)) }

func sha256Bytes(value []byte) string {
	sum := sha256.Sum256(value)
	return "sha256:" + hex.EncodeToString(sum[:])
}

type requiredIndex struct {
	name   string
	keys   bson.D
	unique bool
}

func (s *ContentCandidateStore) inspectQueryIndexes(ctx context.Context) error {
	if s.candidates == nil || s.nodes == nil {
		return errors.New("tag content candidate database is required")
	}
	checks := []struct {
		collection *mongo.Collection
		indexes    []requiredIndex
	}{
		{s.candidates, []requiredIndex{
			{name: ContentCandidateIdentityIndex, keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}}, unique: true},
			{name: ContentCandidateReleaseFenceIndex, keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}}, unique: true},
		}},
		{s.nodes, []requiredIndex{
			{name: TagNodeReleaseTagRefIndex, keys: bson.D{{Key: "releaseId", Value: int32(1)}, {Key: "tagRef", Value: int32(1)}}, unique: true},
			{name: TagNodeReleaseLifecycleIndex, keys: bson.D{{Key: "releaseId", Value: int32(1)}, {Key: "lifecycleStatus", Value: int32(1)}, {Key: "group", Value: int32(1)}, {Key: "depth", Value: int32(1)}, {Key: "tagRef", Value: int32(1)}}},
			{name: TagNodeReleaseParentIndex, keys: bson.D{{Key: "releaseId", Value: int32(1)}, {Key: "parentTagRef", Value: int32(1)}, {Key: "lifecycleStatus", Value: int32(1)}, {Key: "tagRef", Value: int32(1)}}},
			{name: TagNodeReleaseKindIndex, keys: bson.D{{Key: "releaseId", Value: int32(1)}, {Key: "lifecycleStatus", Value: int32(1)}, {Key: "nodeKind", Value: int32(1)}, {Key: "group", Value: int32(1)}, {Key: "tagRef", Value: int32(1)}}},
		}},
	}
	for _, check := range checks {
		cursor, err := check.collection.Indexes().List(ctx)
		if err != nil {
			return fmt.Errorf("inspect Tag release query indexes: %w", err)
		}
		var actual []struct {
			Name   string `bson:"name"`
			Key    bson.D `bson:"key"`
			Unique bool   `bson:"unique"`
		}
		if err := cursor.All(ctx, &actual); err != nil {
			return fmt.Errorf("decode Tag release query indexes: %w", err)
		}
		for _, required := range check.indexes {
			found := false
			for _, index := range actual {
				if index.Name != required.name {
					continue
				}
				found = true
				if index.Unique != required.unique || !sameIndexKeys(index.Key, required.keys) {
					return fmt.Errorf("GATE_BLOCK: incompatible Tag release index %s.%s", check.collection.Name(), required.name)
				}
			}
			if !found {
				return fmt.Errorf("GATE_BLOCK: required Tag release index %s.%s is absent", check.collection.Name(), required.name)
			}
		}
	}
	return nil
}

func sameIndexKeys(left, right bson.D) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index].Key != right[index].Key || fmt.Sprint(left[index].Value) != fmt.Sprint(right[index].Value) {
			return false
		}
	}
	return true
}

// BuildContentCandidate derives a verified candidate from the already
// persisted exact release node snapshot. It is exported for the importer and
// for release-control integration tests; it performs no writes.
func (s *ContentCandidateStore) BuildContentCandidate(
	ctx context.Context,
	environment, sourceOwner, releaseID, manifestDigest, releaseKind string,
	projectionVersion int64,
	verifiedAt time.Time,
) (ContentCandidate, error) {
	nodes, err := s.readCanonicalNodes(ctx, strings.TrimSpace(releaseID))
	if err != nil {
		return ContentCandidate{}, err
	}
	canonical, err := digestCanonicalNodes(nodes)
	if err != nil {
		return ContentCandidate{}, err
	}
	closure, err := digestNodeClosure(nodes)
	if err != nil {
		return ContentCandidate{}, err
	}
	candidate := ContentCandidate{
		Environment: strings.TrimSpace(environment), SourceOwner: strings.TrimSpace(sourceOwner),
		ReleaseID: strings.TrimSpace(releaseID), ManifestDigest: strings.TrimSpace(manifestDigest),
		Status: "verified", ProjectionVersion: projectionVersion, VerifiedAt: verifiedAt.UTC(),
		ClosureDigest: closure, ExpectedNodeCount: len(nodes), ProjectedNodeCount: len(nodes),
		CanonicalDigest: canonical, ReleaseKind: strings.TrimSpace(releaseKind),
		TagRefsDigest: digestTagRefs(nodes),
	}
	if err := validateContentCandidate(candidate); err != nil {
		return ContentCandidate{}, err
	}
	return candidate, nil
}
