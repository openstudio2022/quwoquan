package mediaimagereprocessrun

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

const MaxRunAssets = 500

var (
	ErrInvalidRun         = errors.New("invalid media image reprocess run")
	ErrInvalidRunStatus   = errors.New("invalid media image reprocess run status")
	ErrRunNotFound        = errors.New("media image reprocess run not found")
	ErrRunVersionConflict = errors.New("media image reprocess run version conflict")
)

type Status string

const (
	StatusRunning     Status = "running"
	StatusPaused      Status = "paused"
	StatusRollingBack Status = "rolling_back"
	StatusCompleted   Status = "completed"
	StatusFailed      Status = "failed"
	StatusRolledBack  Status = "rolled_back"
)

type Activation struct {
	AssetID           string
	PreviousRevision  int
	ActivatedRevision int
	ActivatedAt       time.Time
}

type Snapshot struct {
	RunID                         string
	Version                       int64
	TargetDerivativePolicyVersion int
	Status                        Status
	AssetIDs                      []string
	NextAssetIndex                int
	ProcessedCount                int
	FailedCount                   int
	RollbackIndex                 int
	Activations                   []Activation
	FailureReason                 string
	StartedAt                     time.Time
	PausedAt                      *time.Time
	CompletedAt                   *time.Time
	RolledBackAt                  *time.Time
	UpdatedAt                     time.Time
}

type StartParams struct {
	RunID                         string
	TargetDerivativePolicyVersion int
	AssetIDs                      []string
	Now                           time.Time
}

// Run owns bounded orchestration state only. MediaAsset owns descriptor
// revisions and their CAS activation, preserving one media state machine.
type Run struct {
	runID                         string
	version                       int64
	targetDerivativePolicyVersion int
	status                        Status
	assetIDs                      []string
	nextAssetIndex                int
	processedCount                int
	failedCount                   int
	rollbackIndex                 int
	activations                   []Activation
	failureReason                 string
	startedAt                     time.Time
	pausedAt                      *time.Time
	completedAt                   *time.Time
	rolledBackAt                  *time.Time
	updatedAt                     time.Time
}

func Start(params StartParams) (*Run, error) {
	now := params.Now.UTC()
	run := &Run{
		runID:                         strings.TrimSpace(params.RunID),
		version:                       1,
		targetDerivativePolicyVersion: params.TargetDerivativePolicyVersion,
		status:                        StatusRunning,
		assetIDs:                      normalizeAssetIDs(params.AssetIDs),
		startedAt:                     now,
		updatedAt:                     now,
	}
	if err := run.validate(); err != nil {
		return nil, err
	}
	return run, nil
}

func Restore(snapshot Snapshot) (*Run, error) {
	run := &Run{
		runID:                         strings.TrimSpace(snapshot.RunID),
		version:                       snapshot.Version,
		targetDerivativePolicyVersion: snapshot.TargetDerivativePolicyVersion,
		status:                        snapshot.Status,
		assetIDs:                      append([]string(nil), snapshot.AssetIDs...),
		nextAssetIndex:                snapshot.NextAssetIndex,
		processedCount:                snapshot.ProcessedCount,
		failedCount:                   snapshot.FailedCount,
		rollbackIndex:                 snapshot.RollbackIndex,
		activations:                   cloneActivations(snapshot.Activations),
		failureReason:                 strings.TrimSpace(snapshot.FailureReason),
		startedAt:                     snapshot.StartedAt.UTC(),
		pausedAt:                      cloneTime(snapshot.PausedAt),
		completedAt:                   cloneTime(snapshot.CompletedAt),
		rolledBackAt:                  cloneTime(snapshot.RolledBackAt),
		updatedAt:                     snapshot.UpdatedAt.UTC(),
	}
	if err := run.validate(); err != nil {
		return nil, err
	}
	return run, nil
}

func (r *Run) Pause(now time.Time) error {
	if r == nil || r.status != StatusRunning {
		return fmt.Errorf("%w: pause requires running state", ErrInvalidRunStatus)
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.status = StatusPaused
	pausedAt := r.updatedAt
	r.pausedAt = &pausedAt
	return nil
}

func (r *Run) Resume(now time.Time) error {
	if r == nil || r.status != StatusPaused {
		return fmt.Errorf("%w: resume requires paused state", ErrInvalidRunStatus)
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.status = StatusRunning
	r.pausedAt = nil
	return nil
}

// RecordAssetOutcome advances the durable cursor after the MediaAsset command
// has committed. Content rejections are recorded and the run continues; retryable
// infrastructure errors must not call this method.
func (r *Run) RecordAssetOutcome(
	assetID string,
	activation *Activation,
	contentFailure string,
	now time.Time,
) error {
	if r == nil || r.status != StatusRunning || r.nextAssetIndex >= len(r.assetIDs) {
		return fmt.Errorf("%w: no runnable asset outcome", ErrInvalidRunStatus)
	}
	expectedAssetID := r.assetIDs[r.nextAssetIndex]
	if strings.TrimSpace(assetID) != expectedAssetID {
		return fmt.Errorf("%w: outcome does not match durable cursor", ErrInvalidRun)
	}
	if (activation == nil) == (strings.TrimSpace(contentFailure) == "") {
		return fmt.Errorf("%w: outcome must be exactly activation or content failure", ErrInvalidRun)
	}
	if activation != nil {
		if activation.AssetID != expectedAssetID || activation.PreviousRevision <= 0 ||
			activation.ActivatedRevision <= 0 || activation.ActivatedAt.IsZero() {
			return fmt.Errorf("%w: activation audit is invalid", ErrInvalidRun)
		}
		if r.activationIndex(activation.AssetID) >= 0 {
			return fmt.Errorf("%w: asset was activated twice", ErrInvalidRun)
		}
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.nextAssetIndex++
	if activation != nil {
		copy := *activation
		copy.ActivatedAt = copy.ActivatedAt.UTC()
		r.activations = append(r.activations, copy)
		r.processedCount++
	} else {
		r.failedCount++
		r.failureReason = strings.TrimSpace(contentFailure)
	}
	if r.nextAssetIndex == len(r.assetIDs) {
		r.status = StatusCompleted
		completedAt := r.updatedAt
		r.completedAt = &completedAt
	}
	return nil
}

func (r *Run) StartRollback(now time.Time) error {
	if r == nil || (r.status != StatusPaused && r.status != StatusCompleted && r.status != StatusFailed) {
		return fmt.Errorf("%w: rollback requires paused, completed, or failed state", ErrInvalidRunStatus)
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.status = StatusRollingBack
	r.rollbackIndex = len(r.activations)
	return nil
}

func (r *Run) NextRollbackActivation() (Activation, bool) {
	if r == nil || r.status != StatusRollingBack || r.rollbackIndex <= 0 {
		return Activation{}, false
	}
	return r.activations[r.rollbackIndex-1], true
}

func (r *Run) RecordRollback(activation Activation, now time.Time) error {
	if r == nil || r.status != StatusRollingBack || r.rollbackIndex <= 0 {
		return fmt.Errorf("%w: no rollback activation is pending", ErrInvalidRunStatus)
	}
	expected := r.activations[r.rollbackIndex-1]
	if expected != activation {
		return fmt.Errorf("%w: rollback activation order changed", ErrInvalidRun)
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.rollbackIndex--
	if r.rollbackIndex == 0 {
		r.status = StatusRolledBack
		rolledBackAt := r.updatedAt
		r.rolledBackAt = &rolledBackAt
	}
	return nil
}

func (r *Run) NextAssetID() (string, bool) {
	if r == nil || r.status != StatusRunning || r.nextAssetIndex >= len(r.assetIDs) {
		return "", false
	}
	return r.assetIDs[r.nextAssetIndex], true
}

func (r *Run) RunID() string {
	if r == nil {
		return ""
	}
	return r.runID
}
func (r *Run) Version() int64 {
	if r == nil {
		return 0
	}
	return r.version
}
func (r *Run) Status() Status {
	if r == nil {
		return ""
	}
	return r.status
}
func (r *Run) TargetDerivativePolicyVersion() int {
	if r == nil {
		return 0
	}
	return r.targetDerivativePolicyVersion
}

func (r *Run) Snapshot() Snapshot {
	if r == nil {
		return Snapshot{}
	}
	return Snapshot{
		RunID:                         r.runID,
		Version:                       r.version,
		TargetDerivativePolicyVersion: r.targetDerivativePolicyVersion,
		Status:                        r.status,
		AssetIDs:                      append([]string(nil), r.assetIDs...),
		NextAssetIndex:                r.nextAssetIndex,
		ProcessedCount:                r.processedCount,
		FailedCount:                   r.failedCount,
		RollbackIndex:                 r.rollbackIndex,
		Activations:                   cloneActivations(r.activations),
		FailureReason:                 r.failureReason,
		StartedAt:                     r.startedAt,
		PausedAt:                      cloneTime(r.pausedAt),
		CompletedAt:                   cloneTime(r.completedAt),
		RolledBackAt:                  cloneTime(r.rolledBackAt),
		UpdatedAt:                     r.updatedAt,
	}
}

func (r *Run) activationIndex(assetID string) int {
	for index, activation := range r.activations {
		if activation.AssetID == assetID {
			return index
		}
	}
	return -1
}

func (r *Run) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(r.updatedAt) {
		return fmt.Errorf("%w: timestamp is invalid", ErrInvalidRun)
	}
	r.version++
	r.updatedAt = now
	return nil
}

func (r *Run) validate() error {
	if r == nil || r.runID == "" || r.version < 1 ||
		r.targetDerivativePolicyVersion <= 0 || !validStatus(r.status) ||
		len(r.assetIDs) == 0 || len(r.assetIDs) > MaxRunAssets ||
		r.nextAssetIndex < 0 || r.nextAssetIndex > len(r.assetIDs) ||
		r.processedCount < 0 || r.failedCount < 0 ||
		r.processedCount+r.failedCount != r.nextAssetIndex ||
		len(r.activations) != r.processedCount || r.rollbackIndex < 0 ||
		r.rollbackIndex > len(r.activations) || r.startedAt.IsZero() ||
		r.updatedAt.IsZero() || r.updatedAt.Before(r.startedAt) {
		return fmt.Errorf("%w: state is incomplete", ErrInvalidRun)
	}
	seen := make(map[string]struct{}, len(r.assetIDs))
	for _, assetID := range r.assetIDs {
		if assetID == "" {
			return fmt.Errorf("%w: asset id is required", ErrInvalidRun)
		}
		if _, exists := seen[assetID]; exists {
			return fmt.Errorf("%w: asset ids must be unique", ErrInvalidRun)
		}
		seen[assetID] = struct{}{}
	}
	for _, activation := range r.activations {
		if activation.AssetID == "" || activation.PreviousRevision <= 0 ||
			activation.ActivatedRevision <= 0 || activation.ActivatedAt.IsZero() {
			return fmt.Errorf("%w: activation audit is incomplete", ErrInvalidRun)
		}
	}
	switch r.status {
	case StatusRunning:
		if r.completedAt != nil || r.rolledBackAt != nil {
			return fmt.Errorf("%w: running timestamps are invalid", ErrInvalidRun)
		}
	case StatusPaused:
		if r.pausedAt == nil || r.completedAt != nil || r.rolledBackAt != nil {
			return fmt.Errorf("%w: paused timestamps are invalid", ErrInvalidRun)
		}
	case StatusRollingBack:
		if r.rolledBackAt != nil {
			return fmt.Errorf("%w: rolling-back timestamp is invalid", ErrInvalidRun)
		}
	case StatusCompleted:
		if r.nextAssetIndex != len(r.assetIDs) || r.completedAt == nil {
			return fmt.Errorf("%w: completed state is incomplete", ErrInvalidRun)
		}
	case StatusRolledBack:
		if r.rollbackIndex != 0 || r.rolledBackAt == nil {
			return fmt.Errorf("%w: rolled-back state is incomplete", ErrInvalidRun)
		}
	}
	return nil
}

func normalizeAssetIDs(raw []string) []string {
	result := make([]string, 0, len(raw))
	for _, value := range raw {
		result = append(result, strings.TrimSpace(value))
	}
	return result
}

func cloneActivations(activations []Activation) []Activation {
	if len(activations) == 0 {
		return nil
	}
	result := make([]Activation, len(activations))
	copy(result, activations)
	for index := range result {
		result[index].ActivatedAt = result[index].ActivatedAt.UTC()
	}
	return result
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}

func validStatus(status Status) bool {
	switch status {
	case StatusRunning, StatusPaused, StatusRollingBack, StatusCompleted, StatusFailed, StatusRolledBack:
		return true
	default:
		return false
	}
}
