package releaseimport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	ContentLegacyReleaseStateMigrationReceiptSchema = "quwoquan.content_legacy_release_state_migration_receipt.v1"
	LegacyReleaseStateIndexSetV1                    = "content_release_state_legacy_v1"
	LegacyReleaseStageReceiptIndexSetV1             = "content_release_stage_receipt_legacy_v1"
	ContentReleaseStageReceiptSourceOwner           = "qwq_data"
	QuiescedAtomicStorageMigrationMode              = "quiesced_atomic"
	ContentReleaseStateQuiescedConfirmation         = "confirmed"

	legacyReleaseStateCandidateIndexName = "uq_data_release_state_environment_candidate"
	legacyReleaseStateActiveIndexName    = "idx_data_release_state_active_pointer"
	currentReleaseStateActiveIndexName   = "uq_data_release_state_active_pointer"
	releaseStageReceiptAttemptIndexName  = "uq_data_release_stage_receipt_attempt"
	releaseStageReceiptTimelineIndexName = "idx_data_release_stage_receipt_timeline"
)

var allowedLegacyReleaseStateFields = map[string]struct{}{
	"_id": {}, "environment": {}, "sourceOwner": {}, "releaseId": {},
	"activeReleaseId": {}, "manifestDigest": {}, "status": {},
	"releaseClass": {}, "projectionVersion": {}, "activatedAt": {},
	"createdAt": {}, "updatedAt": {}, "readback": {}, "mode": {},
	"deletePolicy": {}, "counts": {}, "kind": {}, "revision": {},
}

var allowedLegacyReleaseStageReceiptFields = map[string]struct{}{
	"_id": {}, "environment": {}, "sourceOwner": {}, "releaseId": {},
	"manifestDigest": {}, "stage": {}, "attemptId": {}, "status": {},
	"recordedAt": {}, "durationMs": {}, "attemptedCount": {},
	"successCount": {}, "checkpoint": {}, "firstTypedBlocker": {},
}

// LegacyReleaseStateMigrationExpectation binds the migration to every mutable
// identity field of the one expected active pointer. LegacyIndexSet must name
// the exact historical index definitions; it is not an open-ended version.
type LegacyReleaseStateMigrationExpectation struct {
	Environment           string
	SourceOwner           string
	ReleaseID             string
	ManifestDigest        string
	ReleaseClass          string
	ProjectionVersion     int64
	ActivatedAt           time.Time
	LegacyIndexSet        string
	LegacyReceiptIndexSet string
	ExpectedReceiptCount  int64
	AllowReplay           bool
}

// LegacyReleaseStateMigrationResult is safe to serialize: it intentionally
// contains no Mongo URI, document body, readback payload, or collection data.
type LegacyReleaseStateMigrationResult struct {
	Status                      string
	Environment                 string
	SourceOwner                 string
	ReleaseID                   string
	ManifestDigest              string
	ReleaseClass                string
	ProjectionVersion           int64
	ActivatedAt                 time.Time
	BeforeIndexSetDigest        string
	AfterIndexSetDigest         string
	ReceiptCount                int64
	BeforeReceiptIndexSetDigest string
	AfterReceiptIndexSetDigest  string
	BeforeReceiptRowSetDigest   string
	AfterReceiptRowSetDigest    string
	Steps                       []string
}

type legacyReleaseStateDocument struct {
	ID                any       `bson:"_id"`
	Kind              string    `bson:"kind"`
	Environment       string    `bson:"environment"`
	SourceOwner       string    `bson:"sourceOwner"`
	ReleaseID         string    `bson:"releaseId"`
	ActiveReleaseID   string    `bson:"activeReleaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	Status            string    `bson:"status"`
	ReleaseClass      string    `bson:"releaseClass"`
	ProjectionVersion int64     `bson:"projectionVersion"`
	Revision          int64     `bson:"revision"`
	ActivatedAt       time.Time `bson:"activatedAt"`
}

type releaseStateIndexDefinition struct {
	Name    string `json:"name"`
	Keys    bson.D `json:"keys"`
	Unique  bool   `json:"unique"`
	Partial bson.D `json:"partial,omitempty"`
}

type inspectedReleaseStateIndexes struct {
	CandidateKind string
	LegacyActive  bool
	CurrentActive bool
	Definitions   []releaseStateIndexDefinition
}

type legacyReleaseStageReceiptDocument struct {
	ID                any       `bson:"_id"`
	Environment       string    `bson:"environment"`
	SourceOwner       string    `bson:"sourceOwner"`
	ReleaseID         string    `bson:"releaseId"`
	ManifestDigest    string    `bson:"manifestDigest"`
	Stage             string    `bson:"stage"`
	AttemptID         string    `bson:"attemptId"`
	Status            string    `bson:"status"`
	RecordedAt        time.Time `bson:"recordedAt"`
	DurationMs        int64     `bson:"durationMs"`
	AttemptedCount    int64     `bson:"attemptedCount"`
	SuccessCount      int64     `bson:"successCount"`
	Checkpoint        string    `bson:"checkpoint"`
	FirstTypedBlocker string    `bson:"firstTypedBlocker"`
	StageOrder        int       `bson:"-"`
}

type inspectedReleaseStageReceiptIndexes struct {
	AttemptKind  string
	TimelineKind string
	Definitions  []releaseStateIndexDefinition
}

func legacyReleaseStateIndexDefinitions() []releaseStateIndexDefinition {
	return []releaseStateIndexDefinition{
		{
			Name: legacyReleaseStateActiveIndexName,
			Keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "status", Value: int32(1)}, {Key: "activatedAt", Value: int32(-1)}},
		},
		{
			Name:   legacyReleaseStateCandidateIndexName,
			Keys:   bson.D{{Key: "environment", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}},
			Unique: true,
		},
	}
}

func legacyReleaseStageReceiptIndexDefinitions() []releaseStateIndexDefinition {
	return []releaseStateIndexDefinition{
		{
			Name:   releaseStageReceiptAttemptIndexName,
			Keys:   bson.D{{Key: "environment", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}, {Key: "stage", Value: int32(1)}, {Key: "attemptId", Value: int32(1)}},
			Unique: true,
		},
		{
			Name: releaseStageReceiptTimelineIndexName,
			Keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "recordedAt", Value: int32(1)}},
		},
	}
}

func currentReleaseStageReceiptIndexDefinitions() []releaseStateIndexDefinition {
	return []releaseStateIndexDefinition{
		{
			Name:   releaseStageReceiptAttemptIndexName,
			Keys:   bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}, {Key: "stage", Value: int32(1)}, {Key: "attemptId", Value: int32(1)}},
			Unique: true,
		},
		{
			Name: releaseStageReceiptTimelineIndexName,
			Keys: bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "recordedAt", Value: int32(1)}},
		},
	}
}

func temporaryReleaseStageReceiptIndexDefinition(current releaseStateIndexDefinition) releaseStateIndexDefinition {
	keys := append(bson.D(nil), current.Keys...)
	keys = append(keys, bson.E{Key: "_id", Value: int32(1)})
	return releaseStateIndexDefinition{
		Name: current.Name + "__source_owner_migration",
		Keys: keys,
	}
}

func currentReleaseStateIndexDefinitions() []releaseStateIndexDefinition {
	return []releaseStateIndexDefinition{
		{
			Name:    currentReleaseStateActiveIndexName,
			Keys:    bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "kind", Value: int32(1)}},
			Unique:  true,
			Partial: bson.D{{Key: "kind", Value: releaseActivePointerKind}},
		},
		{
			Name:    legacyReleaseStateCandidateIndexName,
			Keys:    bson.D{{Key: "environment", Value: int32(1)}, {Key: "sourceOwner", Value: int32(1)}, {Key: "kind", Value: int32(1)}, {Key: "releaseId", Value: int32(1)}, {Key: "manifestDigest", Value: int32(1)}},
			Unique:  true,
			Partial: bson.D{{Key: "kind", Value: releaseCandidateKind}},
		},
	}
}

// LegacyReleaseStateExpectedIndexDigest returns the stable digest operators can
// use to independently bind an approval to the hard-coded legacy definition.
func LegacyReleaseStateExpectedIndexDigest() string {
	return releaseStateIndexSetDigest(legacyReleaseStateIndexDefinitions())
}

// CurrentReleaseStateExpectedIndexDigest identifies the exact post-migration
// index set revalidated before a success receipt may be emitted.
func CurrentReleaseStateExpectedIndexDigest() string {
	return releaseStateIndexSetDigest(currentReleaseStateIndexDefinitions())
}

// LegacyReleaseStageReceiptExpectedIndexDigest binds the migration to the two
// exact historical receipt index definitions.
func LegacyReleaseStageReceiptExpectedIndexDigest() string {
	return releaseStateIndexSetDigest(legacyReleaseStageReceiptIndexDefinitions())
}

// CurrentReleaseStageReceiptExpectedIndexDigest identifies the exact owner-
// scoped receipt index set required after migration.
func CurrentReleaseStageReceiptExpectedIndexDigest() string {
	return releaseStateIndexSetDigest(currentReleaseStageReceiptIndexDefinitions())
}

func releaseStateIndexSetDigest(definitions []releaseStateIndexDefinition) string {
	ordered := append([]releaseStateIndexDefinition(nil), definitions...)
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].Name < ordered[j].Name })
	encoded, err := json.Marshal(ordered)
	if err != nil {
		panic(fmt.Sprintf("encode release state index definition: %v", err))
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func validateLegacyReleaseStateMigrationExpectation(expectation LegacyReleaseStateMigrationExpectation) (LegacyReleaseStateMigrationExpectation, error) {
	expectation.Environment = strings.TrimSpace(expectation.Environment)
	expectation.SourceOwner = strings.TrimSpace(expectation.SourceOwner)
	expectation.ReleaseID = strings.TrimSpace(expectation.ReleaseID)
	expectation.ManifestDigest = strings.TrimSpace(expectation.ManifestDigest)
	expectation.ReleaseClass = strings.TrimSpace(expectation.ReleaseClass)
	expectation.LegacyIndexSet = strings.TrimSpace(expectation.LegacyIndexSet)
	expectation.LegacyReceiptIndexSet = strings.TrimSpace(expectation.LegacyReceiptIndexSet)
	expectation.ActivatedAt = expectation.ActivatedAt.UTC()
	if expectation.Environment == "" || expectation.SourceOwner != ContentReleaseStageReceiptSourceOwner || expectation.ReleaseID == "" ||
		!sha256Pattern.MatchString(expectation.ManifestDigest) {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-state expected current identity is incomplete or non-canonical")
	}
	if expectation.ReleaseClass != "research" && expectation.ReleaseClass != "commercial" {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-state expected release class must be research or commercial")
	}
	if expectation.ProjectionVersion <= 0 || expectation.ActivatedAt.IsZero() {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-state expected projection version and activatedAt are required")
	}
	if !expectation.ActivatedAt.Equal(expectation.ActivatedAt.Truncate(time.Millisecond)) {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-state expected activatedAt must have MongoDB millisecond precision")
	}
	if expectation.LegacyIndexSet != LegacyReleaseStateIndexSetV1 {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-state index expectation must be %q", LegacyReleaseStateIndexSetV1)
	}
	if expectation.LegacyReceiptIndexSet != LegacyReleaseStageReceiptIndexSetV1 {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-stage receipt index expectation must be %q", LegacyReleaseStageReceiptIndexSetV1)
	}
	if expectation.ExpectedReceiptCount < 0 {
		return LegacyReleaseStateMigrationExpectation{}, fmt.Errorf("legacy release-stage receipt expected row count must be non-negative")
	}
	return expectation, nil
}

// MigrateLegacyContentReleaseState converts the only data_release_state row and
// every recognized historical data_release_stage_receipts row. Documents are
// changed before their indexes because MongoDB index DDL cannot be part of the
// document transaction. Every DDL phase is deliberately replayable: the
// replacement index is first built under a temporary name, the historical
// index is then dropped, and the canonical current index is created before the
// temporary safety index is removed.
func MigrateLegacyContentReleaseState(
	ctx context.Context,
	database *mongo.Database,
	expectation LegacyReleaseStateMigrationExpectation,
) (LegacyReleaseStateMigrationResult, error) {
	if ctx == nil || database == nil {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("legacy release-state migration context and database are required")
	}
	expectation, err := validateLegacyReleaseStateMigrationExpectation(expectation)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	state := database.Collection("data_release_state")
	receipts := database.Collection("data_release_stage_receipts")
	if err := requireEmptyLegacyReleaseCandidateCollections(ctx, database); err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	_, document, stateCurrent, err := inspectOnlyLegacyReleaseStateDocument(ctx, state, expectation)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	stateIndexes, err := inspectLegacyReleaseStateIndexes(ctx, state)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	beforeStateDigest := releaseStateIndexSetDigest(stateIndexes.Definitions)
	if !stateCurrent {
		if !isExactLegacyReleaseStateIndexSet(stateIndexes) {
			return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: legacy data_release_state indexes differ from %s (expected digest %s, actual %s)", LegacyReleaseStateIndexSetV1, LegacyReleaseStateExpectedIndexDigest(), beforeStateDigest)
		}
	} else {
		if !expectation.AllowReplay {
			return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: current or partially migrated release state requires explicit --allow-replay")
		}
		if !isRecoverableCurrentReleaseStateIndexSet(stateIndexes) {
			return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: current release-state index set is not a recognized recoverable migration phase")
		}
	}

	receiptIndexes, err := inspectLegacyReleaseStageReceiptIndexes(ctx, receipts)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	beforeReceiptDigest := releaseStateIndexSetDigest(receiptIndexes.Definitions)
	receiptDocuments, beforeReceiptRows, receiptsCurrent, err := inspectLegacyReleaseStageReceiptDocuments(ctx, receipts, expectation)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	if int64(len(receiptDocuments)) != expectation.ExpectedReceiptCount {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: release-stage receipt row count differs from exact expectation: expected %d, found %d", expectation.ExpectedReceiptCount, len(receiptDocuments))
	}
	receiptsMixed := false
	if !receiptsCurrent {
		for _, document := range receiptDocuments {
			if document.SourceOwner == expectation.SourceOwner {
				receiptsMixed = true
				break
			}
		}
	}
	beforeReceiptRowDigest := releaseStageReceiptRawRowSetDigest(beforeReceiptRows)
	beforeReceiptPreservationDigest := releaseStageReceiptRowSetDigest(beforeReceiptRows, expectation.SourceOwner)
	if len(receiptDocuments) == 0 {
		receiptsCurrent = !isExactLegacyReleaseStageReceiptIndexSet(receiptIndexes)
	}
	if !stateCurrent {
		if receiptsCurrent || receiptsMixed {
			return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: current or mixed release-stage receipts with legacy release state are not a recognized migration phase")
		}
		if !isExactLegacyReleaseStageReceiptIndexSet(receiptIndexes) {
			return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: legacy data_release_stage_receipts indexes differ from %s (expected digest %s, actual %s)", LegacyReleaseStageReceiptIndexSetV1, LegacyReleaseStageReceiptExpectedIndexDigest(), beforeReceiptDigest)
		}
	} else if !isExactLegacyReleaseStageReceiptIndexSet(receiptIndexes) &&
		!isRecoverableCurrentReleaseStageReceiptIndexSet(receiptIndexes) {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: current release-stage receipt index set is not a recognized recoverable migration phase")
	}

	steps := make([]string, 0, 14)
	status := "migrated"
	if stateCurrent || receiptsCurrent {
		status = "resumed"
	}
	stateChanged, receiptsChanged, err := migrateLegacyReleaseControlDocuments(
		ctx, state, receipts, expectation, document, receiptDocuments, stateCurrent, receiptsCurrent,
	)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	if stateChanged {
		steps = append(steps, "cas-active-pointer-document")
	}
	if receiptsChanged {
		steps = append(steps, "bulk-cas-release-stage-receipt-owner")
	}

	if err := migrateLegacyReleaseStateIndexes(ctx, state, &stateIndexes, &steps); err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	if err := migrateLegacyReleaseStageReceiptIndexes(ctx, receipts, &receiptIndexes, &steps); err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}

	if err := requireEmptyLegacyReleaseCandidateCollections(ctx, database); err != nil {
		return LegacyReleaseStateMigrationResult{}, err
	}
	_, readback, readbackCurrent, err := inspectOnlyLegacyReleaseStateDocument(ctx, state, expectation)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("revalidate migrated release-state document: %w", err)
	}
	if !readbackCurrent || readback.Kind != releaseActivePointerKind || readback.Revision != 1 {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: migrated release-state readback is not current")
	}
	finalStateIndexes, err := inspectLegacyReleaseStateIndexes(ctx, state)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("revalidate migrated release-state indexes: %w", err)
	}
	if !isExactCurrentReleaseStateIndexSet(finalStateIndexes) {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: migrated release-state indexes failed exact readback")
	}
	readbackReceipts, afterReceiptRows, readbackReceiptsCurrent, err := inspectLegacyReleaseStageReceiptDocuments(ctx, receipts, expectation)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("revalidate migrated release-stage receipt documents: %w", err)
	}
	if !readbackReceiptsCurrent || len(readbackReceipts) != len(receiptDocuments) {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: migrated release-stage receipt readback is not current")
	}
	afterReceiptRowDigest := releaseStageReceiptRawRowSetDigest(afterReceiptRows)
	if releaseStageReceiptRowSetDigest(afterReceiptRows, expectation.SourceOwner) != beforeReceiptPreservationDigest {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: migrated release-stage receipt non-owner row-set digest changed")
	}
	finalReceiptIndexes, err := inspectLegacyReleaseStageReceiptIndexes(ctx, receipts)
	if err != nil {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("revalidate migrated release-stage receipt indexes: %w", err)
	}
	if !isExactCurrentReleaseStageReceiptIndexSet(finalReceiptIndexes) {
		return LegacyReleaseStateMigrationResult{}, fmt.Errorf("GATE_BLOCK: migrated release-stage receipt indexes failed exact readback")
	}
	if stateCurrent && receiptsCurrent && len(steps) == 0 {
		status = "replayed"
	}
	return LegacyReleaseStateMigrationResult{
		Status: status, Environment: expectation.Environment, SourceOwner: expectation.SourceOwner,
		ReleaseID: expectation.ReleaseID, ManifestDigest: expectation.ManifestDigest,
		ReleaseClass: expectation.ReleaseClass, ProjectionVersion: expectation.ProjectionVersion,
		ActivatedAt: expectation.ActivatedAt, BeforeIndexSetDigest: beforeStateDigest,
		AfterIndexSetDigest: releaseStateIndexSetDigest(finalStateIndexes.Definitions),
		ReceiptCount:        int64(len(readbackReceipts)), BeforeReceiptIndexSetDigest: beforeReceiptDigest,
		AfterReceiptIndexSetDigest: releaseStateIndexSetDigest(finalReceiptIndexes.Definitions),
		BeforeReceiptRowSetDigest:  beforeReceiptRowDigest,
		AfterReceiptRowSetDigest:   afterReceiptRowDigest,
		Steps:                      steps,
	}, nil
}

func inspectLegacyReleaseStageReceiptDocuments(
	ctx context.Context,
	receipts *mongo.Collection,
	expectation LegacyReleaseStateMigrationExpectation,
) ([]legacyReleaseStageReceiptDocument, []bson.Raw, bool, error) {
	cursor, err := receipts.Find(ctx, bson.D{}, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return nil, nil, false, fmt.Errorf("inspect data_release_stage_receipts: %w", err)
	}
	defer cursor.Close(ctx)
	var rawDocuments []bson.Raw
	if err := cursor.All(ctx, &rawDocuments); err != nil {
		return nil, nil, false, fmt.Errorf("decode data_release_stage_receipts: %w", err)
	}
	documents := make([]legacyReleaseStageReceiptDocument, 0, len(rawDocuments))
	legacyCount := 0
	for _, raw := range rawDocuments {
		elements, err := raw.Elements()
		if err != nil {
			return nil, nil, false, fmt.Errorf("decode legacy release-stage receipt fields: %w", err)
		}
		for _, element := range elements {
			if _, allowed := allowedLegacyReleaseStageReceiptFields[element.Key()]; !allowed {
				return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipt contains unexpected field %q", element.Key())
			}
		}
		if err := validateLegacyReleaseStageReceiptRawTypes(raw); err != nil {
			return nil, nil, false, err
		}
		var document legacyReleaseStageReceiptDocument
		if err := bson.Unmarshal(raw, &document); err != nil {
			return nil, nil, false, fmt.Errorf("decode legacy release-stage receipt: %w", err)
		}
		if document.Environment != expectation.Environment {
			return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipt environment differs from exact expected environment")
		}
		if document.SourceOwner != "" && document.SourceOwner != expectation.SourceOwner {
			return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipts contain mixed owner data")
		}
		if err := validateLegacyReleaseStageReceiptDocument(document); err != nil {
			return nil, nil, false, err
		}
		document.StageOrder = map[string]int{"prepared": 0, "imported": 1, "projected": 2, "verified": 3, "active": 4}[document.Stage]
		if document.SourceOwner == "" {
			legacyCount++
		}
		documents = append(documents, document)
	}
	identities := make(map[string]struct{}, len(documents))
	releaseDigests := make(map[string]string)
	digestReleases := make(map[string]string)
	for _, document := range documents {
		identity := strings.Join([]string{
			document.Environment, expectation.SourceOwner, document.ReleaseID,
			document.ManifestDigest, document.Stage, document.AttemptID,
		}, "\x00")
		if _, exists := identities[identity]; exists {
			return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipt owner binding would collide")
		}
		identities[identity] = struct{}{}
		if digest, exists := releaseDigests[document.ReleaseID]; exists && digest != document.ManifestDigest {
			return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipt release tuple is ambiguous")
		}
		if releaseID, exists := digestReleases[document.ManifestDigest]; exists && releaseID != document.ReleaseID {
			return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipt manifest tuple is ambiguous")
		}
		releaseDigests[document.ReleaseID] = document.ManifestDigest
		digestReleases[document.ManifestDigest] = document.ReleaseID
	}
	byAttempt := make(map[string][]legacyReleaseStageReceiptDocument)
	for _, document := range documents {
		key := strings.Join([]string{document.ReleaseID, document.ManifestDigest, document.AttemptID}, "\x00")
		byAttempt[key] = append(byAttempt[key], document)
	}
	for _, attempt := range byAttempt {
		sort.Slice(attempt, func(left, right int) bool { return attempt[left].StageOrder < attempt[right].StageOrder })
		for index := 1; index < len(attempt); index++ {
			if attempt[index-1].StageOrder >= attempt[index].StageOrder ||
				(!attempt[index-1].RecordedAt.Equal(attempt[index].RecordedAt) && attempt[index-1].RecordedAt.After(attempt[index].RecordedAt)) {
				return nil, nil, false, fmt.Errorf("GATE_BLOCK: release-stage receipt timeline is ambiguous")
			}
		}
	}
	return documents, rawDocuments, legacyCount == 0, nil
}

func validateLegacyReleaseStageReceiptRawTypes(raw bson.Raw) error {
	stringFields := []string{"environment", "releaseId", "manifestDigest", "stage", "attemptId", "status", "checkpoint"}
	for _, field := range stringFields {
		if _, ok := raw.Lookup(field).StringValueOK(); !ok {
			return fmt.Errorf("GATE_BLOCK: release-stage receipt field %q has unexpected BSON type", field)
		}
	}
	if owner := raw.Lookup("sourceOwner"); !owner.IsZero() {
		if _, ok := owner.StringValueOK(); !ok {
			return fmt.Errorf("GATE_BLOCK: release-stage receipt field %q has unexpected BSON type", "sourceOwner")
		}
	}
	if _, ok := raw.Lookup("recordedAt").TimeOK(); !ok {
		return fmt.Errorf("GATE_BLOCK: release-stage receipt field %q has unexpected BSON type", "recordedAt")
	}
	for _, field := range []string{"durationMs", "attemptedCount", "successCount"} {
		value := raw.Lookup(field)
		if _, ok := value.Int32OK(); !ok {
			if _, ok := value.Int64OK(); !ok {
				return fmt.Errorf("GATE_BLOCK: release-stage receipt field %q has unexpected BSON type", field)
			}
		}
	}
	if blocker := raw.Lookup("firstTypedBlocker"); !blocker.IsZero() {
		if _, ok := blocker.StringValueOK(); !ok {
			return fmt.Errorf("GATE_BLOCK: release-stage receipt field %q has unexpected BSON type", "firstTypedBlocker")
		}
	}
	return nil
}

func releaseStageReceiptRawRowSetDigest(rawDocuments []bson.Raw) string {
	rows := make([]string, 0, len(rawDocuments))
	for _, raw := range rawDocuments {
		rows = append(rows, string(raw))
	}
	sort.Strings(rows)
	digest := sha256.New()
	for _, row := range rows {
		_, _ = digest.Write([]byte(row))
		_, _ = digest.Write([]byte{0})
	}
	return "sha256:" + hex.EncodeToString(digest.Sum(nil))
}

func releaseStageReceiptRowSetDigest(rawDocuments []bson.Raw, expectedSourceOwner string) string {
	rows := make([]string, 0, len(rawDocuments))
	for _, raw := range rawDocuments {
		var row bson.D
		if err := bson.Unmarshal(raw, &row); err != nil {
			panic(fmt.Sprintf("decode validated release-stage receipt row: %v", err))
		}
		for index := range row {
			if row[index].Key == "sourceOwner" {
				row[index].Value = expectedSourceOwner
				break
			}
		}
		hasOwner := false
		for _, element := range row {
			hasOwner = hasOwner || element.Key == "sourceOwner"
		}
		if !hasOwner {
			row = append(row, bson.E{Key: "sourceOwner", Value: expectedSourceOwner})
		}
		encoded, err := bson.MarshalExtJSON(row, true, false)
		if err != nil {
			panic(fmt.Sprintf("encode validated release-stage receipt row: %v", err))
		}
		rows = append(rows, string(encoded))
	}
	sort.Strings(rows)
	digest := sha256.New()
	for _, row := range rows {
		_, _ = digest.Write([]byte(row))
		_, _ = digest.Write([]byte{0})
	}
	return "sha256:" + hex.EncodeToString(digest.Sum(nil))
}

func validateLegacyReleaseStageReceiptDocument(document legacyReleaseStageReceiptDocument) error {
	if document.ReleaseID != strings.TrimSpace(document.ReleaseID) || document.ReleaseID == "" ||
		strings.ContainsAny(document.ReleaseID, ":\x00") || !sha256Pattern.MatchString(document.ManifestDigest) ||
		document.RecordedAt.IsZero() || document.RecordedAt.UTC() != document.RecordedAt ||
		document.DurationMs < 0 || document.AttemptedCount < 0 || document.SuccessCount < 0 ||
		document.SuccessCount > document.AttemptedCount {
		return fmt.Errorf("GATE_BLOCK: release-stage receipt identity or counts have unexpected shape")
	}
	attemptPrefix := document.Environment + ":" + document.ReleaseID + ":"
	attemptSequence := strings.TrimPrefix(document.AttemptID, attemptPrefix)
	sequence, sequenceErr := strconv.ParseInt(attemptSequence, 10, 64)
	if !strings.HasPrefix(document.AttemptID, attemptPrefix) || sequenceErr != nil || sequence <= 0 {
		return fmt.Errorf("GATE_BLOCK: release-stage receipt attempt identity is ambiguous")
	}
	passedCheckpoints := map[string]string{
		"prepared":  "canonical-input-validated",
		"imported":  "posts-materialized",
		"projected": "lifecycle-outbox-appended",
		"verified":  "counts-and-readback-validated",
		"active":    "active-pointer-committed",
	}
	if document.Status == "passed" {
		if expected, allowed := passedCheckpoints[document.Stage]; !allowed || document.Checkpoint != expected || document.FirstTypedBlocker != "" {
			return fmt.Errorf("GATE_BLOCK: passed release-stage receipt has unexpected shape")
		}
		return nil
	}
	if document.Status != "failed" || document.Stage != "imported" ||
		document.Checkpoint != "transaction-aborted" || document.FirstTypedBlocker != releaseImportFailedBlocker {
		return fmt.Errorf("GATE_BLOCK: failed release-stage receipt has unexpected shape")
	}
	return nil
}

func migrateLegacyReleaseControlDocuments(
	ctx context.Context,
	state *mongo.Collection,
	receipts *mongo.Collection,
	expectation LegacyReleaseStateMigrationExpectation,
	stateDocument legacyReleaseStateDocument,
	receiptDocuments []legacyReleaseStageReceiptDocument,
	stateCurrent bool,
	receiptsCurrent bool,
) (bool, bool, error) {
	if stateCurrent && receiptsCurrent {
		return false, false, nil
	}
	session, err := state.Database().Client().StartSession()
	if err != nil {
		return false, false, fmt.Errorf("start legacy release control CAS transaction: %w", err)
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if !stateCurrent {
			result, updateErr := state.UpdateOne(txCtx, bson.M{
				"_id":         stateDocument.ID,
				"environment": expectation.Environment, "sourceOwner": expectation.SourceOwner,
				"releaseId": expectation.ReleaseID, "activeReleaseId": expectation.ReleaseID,
				"manifestDigest": expectation.ManifestDigest, "releaseClass": expectation.ReleaseClass,
				"projectionVersion": expectation.ProjectionVersion, "activatedAt": expectation.ActivatedAt,
				"status": "active", "kind": bson.M{"$exists": false}, "revision": bson.M{"$exists": false},
			}, bson.M{"$set": bson.M{"kind": releaseActivePointerKind, "revision": int64(1)}})
			if updateErr != nil {
				return nil, fmt.Errorf("CAS legacy Content release-state document: %w", updateErr)
			}
			if result.MatchedCount != 1 || result.ModifiedCount != 1 {
				return nil, fmt.Errorf("GATE_BLOCK: legacy Content release-state expected current CAS conflict")
			}
		}
		if !receiptsCurrent {
			if err := migrateLegacyReleaseStageReceiptDocuments(txCtx, receipts, expectation, receiptDocuments); err != nil {
				return nil, err
			}
		}
		return nil, nil
	})
	if err != nil {
		return false, false, err
	}
	return !stateCurrent, !receiptsCurrent, nil
}

func migrateLegacyReleaseStageReceiptDocuments(
	ctx context.Context,
	receipts *mongo.Collection,
	expectation LegacyReleaseStateMigrationExpectation,
	documents []legacyReleaseStageReceiptDocument,
) error {
	models := make([]mongo.WriteModel, 0, len(documents))
	for _, document := range documents {
		if document.SourceOwner == expectation.SourceOwner {
			continue
		}
		filter := bson.M{
			"_id": document.ID, "environment": expectation.Environment,
			"sourceOwner": bson.M{"$exists": false}, "releaseId": document.ReleaseID,
			"manifestDigest": document.ManifestDigest, "stage": document.Stage,
			"attemptId": document.AttemptID, "status": document.Status,
			"recordedAt": document.RecordedAt, "durationMs": document.DurationMs,
			"attemptedCount": document.AttemptedCount, "successCount": document.SuccessCount,
			"checkpoint": document.Checkpoint,
		}
		if document.FirstTypedBlocker == "" {
			filter["firstTypedBlocker"] = bson.M{"$exists": false}
		} else {
			filter["firstTypedBlocker"] = document.FirstTypedBlocker
		}
		models = append(models, mongo.NewUpdateOneModel().
			SetFilter(filter).
			SetUpdate(bson.M{"$set": bson.M{"sourceOwner": expectation.SourceOwner}}))
	}
	if len(models) == 0 {
		return nil
	}
	result, err := receipts.BulkWrite(ctx, models, options.BulkWrite().SetOrdered(true))
	if err != nil {
		return fmt.Errorf("bulk CAS legacy release-stage receipt owner: %w", err)
	}
	if result.MatchedCount != int64(len(models)) || result.ModifiedCount != int64(len(models)) {
		return fmt.Errorf("GATE_BLOCK: legacy release-stage receipt owner CAS conflict")
	}
	return nil
}

func migrateLegacyReleaseStateIndexes(
	ctx context.Context,
	state *mongo.Collection,
	indexes *inspectedReleaseStateIndexes,
	steps *[]string,
) error {
	if !indexes.CurrentActive {
		if _, err := state.Indexes().CreateOne(ctx, currentActiveReleaseStateIndexModel()); err != nil {
			return fmt.Errorf("create current active-pointer index (replay with --allow-replay is safe): %w", err)
		}
		indexes.CurrentActive = true
		*steps = append(*steps, "create-current-active-pointer-index")
	}
	if indexes.LegacyActive {
		if err := state.Indexes().DropOne(ctx, legacyReleaseStateActiveIndexName); err != nil {
			return fmt.Errorf("drop legacy active-pointer index (replay with --allow-replay is safe): %w", err)
		}
		indexes.LegacyActive = false
		*steps = append(*steps, "drop-legacy-active-pointer-index")
	}
	if indexes.CandidateKind == "legacy" {
		if err := state.Indexes().DropOne(ctx, legacyReleaseStateCandidateIndexName); err != nil {
			return fmt.Errorf("drop legacy candidate index (replay with --allow-replay is safe): %w", err)
		}
		indexes.CandidateKind = ""
		*steps = append(*steps, "drop-legacy-candidate-index")
	}
	if indexes.CandidateKind == "" {
		if _, err := state.Indexes().CreateOne(ctx, currentCandidateReleaseStateIndexModel()); err != nil {
			return fmt.Errorf("create current candidate index (replay with --allow-replay is safe): %w", err)
		}
		indexes.CandidateKind = "current"
		*steps = append(*steps, "create-current-candidate-index")
	}
	return nil
}

func migrateLegacyReleaseStageReceiptIndexes(
	ctx context.Context,
	receipts *mongo.Collection,
	indexes *inspectedReleaseStageReceiptIndexes,
	steps *[]string,
) error {
	phases := []struct {
		canonicalName string
		temporaryName string
		kind          *string
		definition    releaseStateIndexDefinition
	}{
		{releaseStageReceiptAttemptIndexName, releaseStageReceiptAttemptIndexName + "__source_owner_migration", &indexes.AttemptKind, currentReleaseStageReceiptIndexDefinitions()[0]},
		{releaseStageReceiptTimelineIndexName, releaseStageReceiptTimelineIndexName + "__source_owner_migration", &indexes.TimelineKind, currentReleaseStageReceiptIndexDefinitions()[1]},
	}
	for _, phase := range phases {
		if *phase.kind == "current" {
			continue
		}
		if *phase.kind == "legacy" {
			temporary := temporaryReleaseStageReceiptIndexDefinition(phase.definition)
			model := releaseStageReceiptIndexModel(temporary, phase.temporaryName)
			if _, err := receipts.Indexes().CreateOne(ctx, model); err != nil {
				return fmt.Errorf("create temporary current release-stage receipt index %s (replay with --allow-replay is safe): %w", phase.temporaryName, err)
			}
			*phase.kind = "both"
			*steps = append(*steps, "create-"+phase.temporaryName)
		}
		if *phase.kind == "both" {
			if err := receipts.Indexes().DropOne(ctx, phase.canonicalName); err != nil {
				return fmt.Errorf("drop legacy release-stage receipt index %s (replay with --allow-replay is safe): %w", phase.canonicalName, err)
			}
			*phase.kind = "temporary"
			*steps = append(*steps, "drop-legacy-"+phase.canonicalName)
		}
		if *phase.kind == "temporary" {
			if err := receipts.Indexes().DropOne(ctx, phase.temporaryName); err != nil {
				return fmt.Errorf("drop temporary release-stage receipt index %s (replay with --allow-replay is safe): %w", phase.temporaryName, err)
			}
			*phase.kind = "absent"
			*steps = append(*steps, "drop-"+phase.temporaryName)
		}
		if *phase.kind == "current-and-temporary" {
			if err := receipts.Indexes().DropOne(ctx, phase.temporaryName); err != nil {
				return fmt.Errorf("drop temporary release-stage receipt index %s (replay with --allow-replay is safe): %w", phase.temporaryName, err)
			}
			*phase.kind = "current"
			*steps = append(*steps, "drop-"+phase.temporaryName)
			continue
		}
		if *phase.kind == "absent" {
			model := releaseStageReceiptIndexModel(phase.definition, phase.canonicalName)
			if _, err := receipts.Indexes().CreateOne(ctx, model); err != nil {
				return fmt.Errorf("create canonical current release-stage receipt index %s (replay with --allow-replay is safe): %w", phase.canonicalName, err)
			}
			*phase.kind = "current"
			*steps = append(*steps, "create-current-"+phase.canonicalName)
		}
	}
	return nil
}

func releaseStageReceiptIndexModel(definition releaseStateIndexDefinition, name string) mongo.IndexModel {
	indexOptions := options.Index().SetName(name)
	if definition.Unique {
		indexOptions.SetUnique(true)
	}
	return mongo.IndexModel{Keys: definition.Keys, Options: indexOptions}
}

func inspectOnlyLegacyReleaseStateDocument(
	ctx context.Context,
	state *mongo.Collection,
	expectation LegacyReleaseStateMigrationExpectation,
) (bson.Raw, legacyReleaseStateDocument, bool, error) {
	cursor, err := state.Find(ctx, bson.D{}, options.Find().SetLimit(2))
	if err != nil {
		return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("inspect data_release_state: %w", err)
	}
	defer cursor.Close(ctx)
	var documents []bson.Raw
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("decode data_release_state: %w", err)
	}
	if len(documents) != 1 {
		return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("GATE_BLOCK: migration requires exactly one data_release_state document; found %d", len(documents))
	}
	raw := documents[0]
	elements, err := raw.Elements()
	if err != nil {
		return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("decode legacy release-state fields: %w", err)
	}
	for _, element := range elements {
		if _, allowed := allowedLegacyReleaseStateFields[element.Key()]; !allowed {
			return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("GATE_BLOCK: legacy release-state contains unexpected field %q", element.Key())
		}
	}
	var document legacyReleaseStateDocument
	if err := bson.Unmarshal(raw, &document); err != nil {
		return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("decode legacy release-state document: %w", err)
	}
	if document.Environment != expectation.Environment || document.SourceOwner != expectation.SourceOwner ||
		document.ReleaseID != expectation.ReleaseID || document.ActiveReleaseID != expectation.ReleaseID ||
		document.ManifestDigest != expectation.ManifestDigest || document.ReleaseClass != expectation.ReleaseClass ||
		document.ProjectionVersion != expectation.ProjectionVersion || !document.ActivatedAt.Equal(expectation.ActivatedAt) ||
		document.Status != "active" {
		return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("GATE_BLOCK: legacy release-state differs from exact expected current binding")
	}
	hasKind := raw.Lookup("kind").Type != 0
	hasRevision := raw.Lookup("revision").Type != 0
	if !hasKind && !hasRevision {
		return raw, document, false, nil
	}
	if hasKind && hasRevision && document.Kind == releaseActivePointerKind && document.Revision == 1 {
		return raw, document, true, nil
	}
	return nil, legacyReleaseStateDocument{}, false, fmt.Errorf("GATE_BLOCK: release-state kind/revision shape is ambiguous or drifted")
}

func requireEmptyLegacyReleaseCandidateCollections(ctx context.Context, database *mongo.Database) error {
	for _, name := range []string{"data_release_candidate_posts", "data_release_candidate_outbox", "data_release_candidate_media_assets"} {
		count, err := database.Collection(name).CountDocuments(ctx, bson.D{}, options.Count().SetLimit(1))
		if err != nil {
			return fmt.Errorf("inspect %s before release-state migration: %w", name, err)
		}
		if count != 0 {
			return fmt.Errorf("GATE_BLOCK: release-state migration requires empty candidate collections; %s is not empty", name)
		}
	}
	return nil
}

func inspectLegacyReleaseStateIndexes(ctx context.Context, state *mongo.Collection) (inspectedReleaseStateIndexes, error) {
	cursor, err := state.Indexes().List(ctx)
	if err != nil {
		return inspectedReleaseStateIndexes{}, fmt.Errorf("inspect data_release_state indexes: %w", err)
	}
	var rawIndexes []bson.Raw
	if err := cursor.All(ctx, &rawIndexes); err != nil {
		return inspectedReleaseStateIndexes{}, fmt.Errorf("decode data_release_state indexes: %w", err)
	}
	inspected := inspectedReleaseStateIndexes{}
	legacy := legacyReleaseStateIndexDefinitions()
	current := currentReleaseStateIndexDefinitions()
	for _, raw := range rawIndexes {
		var index struct {
			Name    string `bson:"name"`
			Key     bson.D `bson:"key"`
			Unique  bool   `bson:"unique"`
			Partial bson.D `bson:"partialFilterExpression"`
		}
		if err := bson.Unmarshal(raw, &index); err != nil {
			return inspectedReleaseStateIndexes{}, fmt.Errorf("decode data_release_state index: %w", err)
		}
		if index.Name == "_id_" {
			continue
		}
		elements, err := raw.Elements()
		if err != nil {
			return inspectedReleaseStateIndexes{}, fmt.Errorf("decode data_release_state index options: %w", err)
		}
		for _, element := range elements {
			switch element.Key() {
			case "v", "key", "name", "ns", "unique", "partialFilterExpression":
			default:
				return inspectedReleaseStateIndexes{}, fmt.Errorf("GATE_BLOCK: release-state index %q has unexpected option %q", index.Name, element.Key())
			}
		}
		definition := releaseStateIndexDefinition{Name: index.Name, Keys: index.Key, Unique: index.Unique, Partial: index.Partial}
		switch index.Name {
		case legacyReleaseStateCandidateIndexName:
			switch {
			case releaseStateIndexDefinitionEqual(definition, legacy[1]):
				inspected.CandidateKind = "legacy"
			case releaseStateIndexDefinitionEqual(definition, current[1]):
				inspected.CandidateKind = "current"
			default:
				return inspectedReleaseStateIndexes{}, fmt.Errorf("GATE_BLOCK: candidate release-state index definition drifted")
			}
		case legacyReleaseStateActiveIndexName:
			if !releaseStateIndexDefinitionEqual(definition, legacy[0]) {
				return inspectedReleaseStateIndexes{}, fmt.Errorf("GATE_BLOCK: legacy active release-state index definition drifted")
			}
			inspected.LegacyActive = true
		case currentReleaseStateActiveIndexName:
			if !releaseStateIndexDefinitionEqual(definition, current[0]) {
				return inspectedReleaseStateIndexes{}, fmt.Errorf("GATE_BLOCK: current active release-state index definition drifted")
			}
			inspected.CurrentActive = true
		default:
			return inspectedReleaseStateIndexes{}, fmt.Errorf("GATE_BLOCK: unexpected data_release_state index %q", index.Name)
		}
		inspected.Definitions = append(inspected.Definitions, definition)
	}
	return inspected, nil
}

func inspectLegacyReleaseStageReceiptIndexes(
	ctx context.Context,
	receipts *mongo.Collection,
) (inspectedReleaseStageReceiptIndexes, error) {
	cursor, err := receipts.Indexes().List(ctx)
	if err != nil {
		return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("inspect data_release_stage_receipts indexes: %w", err)
	}
	var rawIndexes []bson.Raw
	if err := cursor.All(ctx, &rawIndexes); err != nil {
		return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("decode data_release_stage_receipts indexes: %w", err)
	}
	legacy := legacyReleaseStageReceiptIndexDefinitions()
	current := currentReleaseStageReceiptIndexDefinitions()
	inspected := inspectedReleaseStageReceiptIndexes{}
	for _, raw := range rawIndexes {
		var index struct {
			Name   string `bson:"name"`
			Key    bson.D `bson:"key"`
			Unique bool   `bson:"unique"`
		}
		if err := bson.Unmarshal(raw, &index); err != nil {
			return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("decode data_release_stage_receipts index: %w", err)
		}
		if index.Name == "_id_" {
			continue
		}
		elements, err := raw.Elements()
		if err != nil {
			return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("decode data_release_stage_receipts index options: %w", err)
		}
		for _, element := range elements {
			switch element.Key() {
			case "v", "key", "name", "ns", "unique":
			default:
				return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("GATE_BLOCK: release-stage receipt index %q has unexpected option %q", index.Name, element.Key())
			}
		}
		definition := releaseStateIndexDefinition{Name: index.Name, Keys: index.Key, Unique: index.Unique}
		switch index.Name {
		case releaseStageReceiptAttemptIndexName:
			switch {
			case releaseStateIndexDefinitionEqual(definition, legacy[0]):
				inspected.AttemptKind = "legacy"
			case releaseStateIndexDefinitionEqual(definition, current[0]):
				inspected.AttemptKind = "current"
			default:
				return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("GATE_BLOCK: release-stage receipt attempt index definition drifted")
			}
		case releaseStageReceiptTimelineIndexName:
			switch {
			case releaseStateIndexDefinitionEqual(definition, legacy[1]):
				inspected.TimelineKind = "legacy"
			case releaseStateIndexDefinitionEqual(definition, current[1]):
				inspected.TimelineKind = "current"
			default:
				return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("GATE_BLOCK: release-stage receipt timeline index definition drifted")
			}
		case releaseStageReceiptAttemptIndexName + "__source_owner_migration":
			expected := temporaryReleaseStageReceiptIndexDefinition(current[0])
			if !releaseStateIndexDefinitionEqual(definition, expected) {
				return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("GATE_BLOCK: temporary release-stage receipt attempt index drifted")
			}
		case releaseStageReceiptTimelineIndexName + "__source_owner_migration":
			expected := temporaryReleaseStageReceiptIndexDefinition(current[1])
			if !releaseStateIndexDefinitionEqual(definition, expected) {
				return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("GATE_BLOCK: temporary release-stage receipt timeline index drifted")
			}
		default:
			return inspectedReleaseStageReceiptIndexes{}, fmt.Errorf("GATE_BLOCK: unexpected data_release_stage_receipts index %q", index.Name)
		}
		inspected.Definitions = append(inspected.Definitions, definition)
	}
	inspected.AttemptKind = normalizeReleaseStageReceiptIndexPhase(inspected.AttemptKind, inspected.Definitions, legacy[0], current[0])
	inspected.TimelineKind = normalizeReleaseStageReceiptIndexPhase(inspected.TimelineKind, inspected.Definitions, legacy[1], current[1])
	return inspected, nil
}

func normalizeReleaseStageReceiptIndexPhase(
	kind string,
	definitions []releaseStateIndexDefinition,
	legacy releaseStateIndexDefinition,
	current releaseStateIndexDefinition,
) string {
	temporary := temporaryReleaseStageReceiptIndexDefinition(current)
	hasLegacy := false
	hasCurrent := false
	hasTemporary := false
	for _, definition := range definitions {
		hasLegacy = hasLegacy || releaseStateIndexDefinitionEqual(definition, legacy)
		hasCurrent = hasCurrent || releaseStateIndexDefinitionEqual(definition, current)
		hasTemporary = hasTemporary || releaseStateIndexDefinitionEqual(definition, temporary)
	}
	switch {
	case hasLegacy && !hasCurrent && hasTemporary:
		return "both"
	case !hasLegacy && !hasCurrent && hasTemporary:
		return "temporary"
	case !hasLegacy && !hasCurrent && !hasTemporary:
		return "absent"
	case !hasLegacy && hasCurrent && hasTemporary:
		return "current-and-temporary"
	case !hasLegacy && hasCurrent && !hasTemporary:
		return "current"
	case hasLegacy && !hasCurrent && !hasTemporary:
		return "legacy"
	default:
		return kind
	}
}

func isExactLegacyReleaseStageReceiptIndexSet(indexes inspectedReleaseStageReceiptIndexes) bool {
	return indexes.AttemptKind == "legacy" && indexes.TimelineKind == "legacy" && len(indexes.Definitions) == 2
}

func isExactCurrentReleaseStageReceiptIndexSet(indexes inspectedReleaseStageReceiptIndexes) bool {
	return indexes.AttemptKind == "current" && indexes.TimelineKind == "current" && len(indexes.Definitions) == 2
}

func isRecoverableCurrentReleaseStageReceiptIndexSet(indexes inspectedReleaseStageReceiptIndexes) bool {
	phase := map[string]int{"legacy": 0, "both": 1, "temporary": 2, "absent": 3, "current-and-temporary": 4, "current": 5}
	attempt, attemptOK := phase[indexes.AttemptKind]
	timeline, timelineOK := phase[indexes.TimelineKind]
	if !attemptOK || !timelineOK {
		return false
	}
	return attempt == 5 || timeline == 0
}

func releaseStateIndexDefinitionEqual(left, right releaseStateIndexDefinition) bool {
	return left.Name == right.Name && left.Unique == right.Unique &&
		migrationBSONDocumentEqual(left.Keys, right.Keys) && migrationBSONDocumentEqual(left.Partial, right.Partial)
}

func migrationBSONDocumentEqual(left, right bson.D) bool {
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

func isExactLegacyReleaseStateIndexSet(indexes inspectedReleaseStateIndexes) bool {
	return indexes.CandidateKind == "legacy" && indexes.LegacyActive && !indexes.CurrentActive && len(indexes.Definitions) == 2
}

func isExactCurrentReleaseStateIndexSet(indexes inspectedReleaseStateIndexes) bool {
	return indexes.CandidateKind == "current" && !indexes.LegacyActive && indexes.CurrentActive && len(indexes.Definitions) == 2
}

func isRecoverableCurrentReleaseStateIndexSet(indexes inspectedReleaseStateIndexes) bool {
	if isExactCurrentReleaseStateIndexSet(indexes) {
		return true
	}
	if indexes.CandidateKind == "legacy" {
		return (indexes.LegacyActive && !indexes.CurrentActive && len(indexes.Definitions) == 2) ||
			(indexes.LegacyActive && indexes.CurrentActive && len(indexes.Definitions) == 3) ||
			(!indexes.LegacyActive && indexes.CurrentActive && len(indexes.Definitions) == 2)
	}
	return indexes.CandidateKind == "" && !indexes.LegacyActive && indexes.CurrentActive && len(indexes.Definitions) == 1
}

func currentActiveReleaseStateIndexModel() mongo.IndexModel {
	return mongo.IndexModel{
		Keys: currentReleaseStateIndexDefinitions()[0].Keys,
		Options: options.Index().SetName(currentReleaseStateActiveIndexName).SetUnique(true).
			SetPartialFilterExpression(bson.D{{Key: "kind", Value: releaseActivePointerKind}}),
	}
}

func currentCandidateReleaseStateIndexModel() mongo.IndexModel {
	return mongo.IndexModel{
		Keys: currentReleaseStateIndexDefinitions()[1].Keys,
		Options: options.Index().SetName(legacyReleaseStateCandidateIndexName).SetUnique(true).
			SetPartialFilterExpression(bson.D{{Key: "kind", Value: releaseCandidateKind}}),
	}
}

type LegacyReleaseStateMigrationCommand struct {
	mongoURI   string
	Database   string
	ReportPath string
	Expected   LegacyReleaseStateMigrationExpectation
}

func ParseLegacyReleaseStateMigrationCommand(args []string) (LegacyReleaseStateMigrationCommand, error) {
	set := flag.NewFlagSet("migrate-content-release-state", flag.ContinueOnError)
	set.SetOutput(io.Discard)
	var command LegacyReleaseStateMigrationCommand
	command.Expected.ExpectedReceiptCount = -1
	var activatedAt string
	set.StringVar(&command.mongoURI, "mongo-uri", "", "MongoDB connection URI; MONGO_URI is used when omitted (never written to reports)")
	set.StringVar(&command.Database, "database", "quwoquan_content", "exact Content Mongo database")
	set.StringVar(&command.Expected.Environment, "env", "", "exact environment")
	set.StringVar(&command.Expected.SourceOwner, "source-owner", "", "exact source owner")
	set.StringVar(&command.Expected.ReleaseID, "expected-release-id", "", "exact current release id")
	set.StringVar(&command.Expected.ManifestDigest, "expected-manifest-digest", "", "exact current manifest digest")
	set.StringVar(&command.Expected.ReleaseClass, "expected-release-class", "", "exact current release class")
	set.Int64Var(&command.Expected.ProjectionVersion, "expected-projection-version", 0, "exact current projection version")
	set.StringVar(&activatedAt, "expected-activated-at", "", "exact current activatedAt (RFC3339)")
	set.StringVar(&command.Expected.LegacyIndexSet, "expected-legacy-index-set", "", "exact legacy release-state index expectation")
	set.StringVar(&command.Expected.LegacyReceiptIndexSet, "expected-legacy-receipt-index-set", "", "exact legacy release-stage receipt index expectation")
	set.Int64Var(&command.Expected.ExpectedReceiptCount, "expected-receipt-count", -1, "exact release-stage receipt row count")
	set.BoolVar(&command.Expected.AllowReplay, "allow-replay", false, "explicitly resume or attest recognized current state")
	set.StringVar(&command.ReportPath, "report", "", "create-once migration receipt path")
	if err := set.Parse(args); err != nil {
		return LegacyReleaseStateMigrationCommand{}, fmt.Errorf("parse legacy release-state migration flags: %w", err)
	}
	if set.NArg() != 0 {
		return LegacyReleaseStateMigrationCommand{}, fmt.Errorf("migrate-content-release-state does not accept positional arguments")
	}
	command.mongoURI = strings.TrimSpace(command.mongoURI)
	if command.mongoURI == "" {
		command.mongoURI = strings.TrimSpace(os.Getenv("MONGO_URI"))
	}
	command.Database = strings.TrimSpace(command.Database)
	command.ReportPath = strings.TrimSpace(command.ReportPath)
	if command.mongoURI == "" || command.Database == "" || command.ReportPath == "" || strings.TrimSpace(activatedAt) == "" {
		return LegacyReleaseStateMigrationCommand{}, fmt.Errorf("--mongo-uri, --database, --expected-activated-at, and --report must be non-empty")
	}
	parsedAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(activatedAt))
	if err != nil {
		return LegacyReleaseStateMigrationCommand{}, fmt.Errorf("--expected-activated-at must be RFC3339: %w", err)
	}
	command.Expected.ActivatedAt = parsedAt.UTC()
	command.Expected, err = validateLegacyReleaseStateMigrationExpectation(command.Expected)
	if err != nil {
		return LegacyReleaseStateMigrationCommand{}, err
	}
	return command, nil
}

type ContentLegacyReleaseStateMigrationReceipt struct {
	Schema                      string    `json:"schema"`
	Status                      string    `json:"status"`
	Database                    string    `json:"database"`
	Environment                 string    `json:"environment"`
	SourceOwner                 string    `json:"sourceOwner"`
	ReleaseID                   string    `json:"releaseId"`
	ManifestDigest              string    `json:"manifestDigest"`
	ReleaseClass                string    `json:"releaseClass"`
	ProjectionVersion           int64     `json:"projectionVersion"`
	ActivatedAt                 time.Time `json:"activatedAt"`
	Revision                    int64     `json:"revision"`
	MigrationMode               string    `json:"migrationMode"`
	LegacyIndexSet              string    `json:"legacyIndexSet"`
	LegacyIndexSetDigest        string    `json:"legacyIndexSetDigest"`
	BeforeIndexSetDigest        string    `json:"beforeIndexSetDigest"`
	AfterIndexSetDigest         string    `json:"afterIndexSetDigest"`
	LegacyReceiptIndexSet       string    `json:"legacyReceiptIndexSet"`
	LegacyReceiptIndexSetDigest string    `json:"legacyReceiptIndexSetDigest"`
	BeforeReceiptIndexSetDigest string    `json:"beforeReceiptIndexSetDigest"`
	AfterReceiptIndexSetDigest  string    `json:"afterReceiptIndexSetDigest"`
	ReceiptCount                int64     `json:"receiptCount"`
	BeforeReceiptRowSetDigest   string    `json:"beforeReceiptRowSetDigest"`
	AfterReceiptRowSetDigest    string    `json:"afterReceiptRowSetDigest"`
	CandidateCollections        string    `json:"candidateCollections"`
	Steps                       []string  `json:"steps"`
	GeneratedAt                 time.Time `json:"generatedAt"`
}

func RunLegacyReleaseStateMigration(ctx context.Context, args []string) error {
	if ctx == nil {
		return fmt.Errorf("legacy release-state migration context is required")
	}
	command, err := ParseLegacyReleaseStateMigrationCommand(args)
	if err != nil {
		return err
	}
	if mode := strings.TrimSpace(os.Getenv("QWQ_STORAGE_MIGRATION_MODE")); mode != QuiescedAtomicStorageMigrationMode {
		return fmt.Errorf("legacy release-state migration requires QWQ_STORAGE_MIGRATION_MODE=%s", QuiescedAtomicStorageMigrationMode)
	}
	if confirmation := strings.TrimSpace(os.Getenv("QWQ_CONTENT_RELEASE_STATE_QUIESCED")); confirmation != ContentReleaseStateQuiescedConfirmation {
		return fmt.Errorf("legacy release-state migration requires QWQ_CONTENT_RELEASE_STATE_QUIESCED=%s", ContentReleaseStateQuiescedConfirmation)
	}
	resolvedReport, err := validateLegacyReleaseStateMigrationReportDestination(command.ReportPath)
	if err != nil {
		return err
	}
	client, err := mongo.Connect(options.Client().ApplyURI(command.mongoURI))
	if err != nil {
		return redactedLegacyMigrationMongoError("connect Content MongoDB", command.mongoURI, err)
	}
	defer client.Disconnect(context.Background())
	if err := client.Ping(ctx, nil); err != nil {
		return redactedLegacyMigrationMongoError("ping Content MongoDB", command.mongoURI, err)
	}
	result, err := MigrateLegacyContentReleaseState(ctx, client.Database(command.Database), command.Expected)
	if err != nil {
		return redactedLegacyMigrationMongoError("migrate Content legacy release state", command.mongoURI, err)
	}
	receipt := ContentLegacyReleaseStateMigrationReceipt{
		Schema: ContentLegacyReleaseStateMigrationReceiptSchema, Status: result.Status,
		Database: command.Database, Environment: result.Environment, SourceOwner: result.SourceOwner,
		ReleaseID: result.ReleaseID, ManifestDigest: result.ManifestDigest,
		ReleaseClass: result.ReleaseClass, ProjectionVersion: result.ProjectionVersion,
		ActivatedAt: result.ActivatedAt.UTC(), Revision: 1,
		MigrationMode:               QuiescedAtomicStorageMigrationMode,
		LegacyIndexSet:              command.Expected.LegacyIndexSet,
		LegacyIndexSetDigest:        LegacyReleaseStateExpectedIndexDigest(),
		BeforeIndexSetDigest:        result.BeforeIndexSetDigest,
		AfterIndexSetDigest:         result.AfterIndexSetDigest,
		LegacyReceiptIndexSet:       command.Expected.LegacyReceiptIndexSet,
		LegacyReceiptIndexSetDigest: LegacyReleaseStageReceiptExpectedIndexDigest(),
		BeforeReceiptIndexSetDigest: result.BeforeReceiptIndexSetDigest,
		AfterReceiptIndexSetDigest:  result.AfterReceiptIndexSetDigest,
		ReceiptCount:                result.ReceiptCount,
		BeforeReceiptRowSetDigest:   result.BeforeReceiptRowSetDigest,
		AfterReceiptRowSetDigest:    result.AfterReceiptRowSetDigest,
		CandidateCollections:        "empty", Steps: result.Steps,
		GeneratedAt: time.Now().UTC().Truncate(time.Millisecond),
	}
	return writeLegacyReleaseStateMigrationReceipt(resolvedReport, receipt)
}

func validateLegacyReleaseStateMigrationReportDestination(path string) (string, error) {
	resolved := filepath.Clean(strings.TrimSpace(path))
	if resolved == "." || resolved == string(filepath.Separator) {
		return "", fmt.Errorf("legacy release-state migration report path is invalid")
	}
	if _, err := os.Lstat(resolved); err == nil {
		return "", fmt.Errorf("legacy release-state migration report already exists")
	} else if !errors.Is(err, os.ErrNotExist) {
		return "", fmt.Errorf("inspect legacy release-state migration report destination: %w", err)
	}
	parentInfo, err := os.Lstat(filepath.Dir(resolved))
	if err != nil {
		return "", fmt.Errorf("inspect legacy release-state migration report directory: %w", err)
	}
	if !parentInfo.IsDir() || parentInfo.Mode()&os.ModeSymlink != 0 {
		return "", fmt.Errorf("legacy release-state migration report directory must be a non-symlink directory")
	}
	return resolved, nil
}

func writeLegacyReleaseStateMigrationReceipt(path string, receipt ContentLegacyReleaseStateMigrationReceipt) error {
	encoded, err := json.MarshalIndent(receipt, "", "  ")
	if err != nil {
		return fmt.Errorf("encode legacy release-state migration receipt: %w", err)
	}
	encoded = append(encoded, '\n')
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return fmt.Errorf("create legacy release-state migration receipt: %w", err)
	}
	remove := true
	defer func() {
		_ = file.Close()
		if remove {
			_ = os.Remove(path)
		}
	}()
	if _, err := file.Write(encoded); err != nil {
		return fmt.Errorf("write legacy release-state migration receipt: %w", err)
	}
	if err := file.Sync(); err != nil {
		return fmt.Errorf("sync legacy release-state migration receipt: %w", err)
	}
	if err := file.Close(); err != nil {
		return fmt.Errorf("close legacy release-state migration receipt: %w", err)
	}
	remove = false
	return nil
}

func redactedLegacyMigrationMongoError(prefix, mongoURI string, err error) error {
	message := err.Error()
	for _, secret := range legacyMigrationURISecrets(mongoURI) {
		message = strings.ReplaceAll(message, secret, "<redacted>")
	}
	return fmt.Errorf("%s: %s", prefix, message)
}

func legacyMigrationURISecrets(mongoURI string) []string {
	secrets := []string{mongoURI}
	parsed, err := url.Parse(mongoURI)
	if err == nil && parsed.User != nil {
		if username := parsed.User.Username(); username != "" {
			secrets = append(secrets, username)
		}
		if password, present := parsed.User.Password(); present && password != "" {
			secrets = append(secrets, password)
		}
	}
	sort.Slice(secrets, func(i, j int) bool { return len(secrets[i]) > len(secrets[j]) })
	return secrets
}
