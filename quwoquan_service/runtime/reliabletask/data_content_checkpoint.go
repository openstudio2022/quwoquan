package reliabletask

import (
	"context"
	"errors"
	"strings"
	"sync"
	"time"
)

var dataContentMemoryCheckpoints = struct {
	sync.Mutex
	byStore map[*MemoryStore]map[string]DataContentPartitionCheckpoint
}{
	byStore: map[*MemoryStore]map[string]DataContentPartitionCheckpoint{},
}

func (s *MemoryStore) FlushDataContentPartitionCheckpoint(
	ctx context.Context,
	checkpoint DataContentPartitionCheckpoint,
) error {
	_ = ctx
	key := checkpoint.ExecutionID + "|" + checkpoint.Stage + "|" + checkpoint.PartitionKey
	dataContentMemoryCheckpoints.Lock()
	defer dataContentMemoryCheckpoints.Unlock()
	checkpoints := dataContentMemoryCheckpoints.byStore[s]
	if checkpoints == nil {
		checkpoints = map[string]DataContentPartitionCheckpoint{}
		dataContentMemoryCheckpoints.byStore[s] = checkpoints
	}
	if existing, ok := checkpoints[key]; ok {
		if existing.JobSetDigest != checkpoint.JobSetDigest {
			return errors.New("DATA.RELIABLETASK.STALE_FENCE: partition checkpoint jobSetDigest drift")
		}
		if existing.CompletedCount > checkpoint.CompletedCount {
			return errors.New("DATA.RELIABLETASK.STALE_CHECKPOINT: partition checkpoint cannot move backwards")
		}
	}
	checkpoints[key] = checkpoint
	return nil
}

type dataContentCheckpointProgress struct {
	completedCount int
	flushedAt      time.Time
}

// DataContentCheckpointTracker derives cadence-triggered partition watermarks.
// Commit is called only after the durable store accepts the checkpoint.
type DataContentCheckpointTracker struct {
	epoch    time.Time
	progress map[string]dataContentCheckpointProgress
}

func NewDataContentCheckpointTracker(epoch time.Time) *DataContentCheckpointTracker {
	return &DataContentCheckpointTracker{
		epoch:    epoch.UTC(),
		progress: map[string]dataContentCheckpointProgress{},
	}
}

func (t *DataContentCheckpointTracker) Due(
	executionID string,
	stage string,
	jobSetDigest string,
	tasks []ReliableAsyncTask,
	everyFinalizedObjects int,
	every time.Duration,
	now time.Time,
	force bool,
) ([]DataContentPartitionCheckpoint, error) {
	if t == nil || everyFinalizedObjects < 1 || every <= 0 ||
		strings.TrimSpace(executionID) == "" ||
		(stage != "author" && stage != "publish") ||
		!ValidSHA256Digest(jobSetDigest) {
		return nil, errors.New("data content checkpoint cadence identity is invalid")
	}
	type succeededProgress struct {
		completedCount int
		cursorJobID    string
	}
	succeeded := map[string]succeededProgress{}
	for _, task := range tasks {
		if task.Status != TaskStatusSucceeded {
			continue
		}
		partition := strings.TrimSpace(task.Payload["partitionKey"])
		jobID := strings.TrimSpace(task.Payload["jobId"])
		if partition == "" || jobID == "" {
			return nil, errors.New("succeeded data content task lacks checkpoint identity")
		}
		current := succeeded[partition]
		current.completedCount++
		if current.cursorJobID == "" || jobID > current.cursorJobID {
			current.cursorJobID = jobID
		}
		succeeded[partition] = current
	}
	due := make([]DataContentPartitionCheckpoint, 0, len(succeeded))
	for partition, current := range succeeded {
		previous, exists := t.progress[partition]
		if !exists {
			previous.flushedAt = t.epoch
		}
		if current.completedCount <= previous.completedCount {
			continue
		}
		objectDue := current.completedCount-previous.completedCount >= everyFinalizedObjects
		timeDue := now.Sub(previous.flushedAt) >= every
		if !force && !objectDue && !timeDue {
			continue
		}
		due = append(due, DataContentPartitionCheckpoint{
			ExecutionID:    executionID,
			Stage:          stage,
			PartitionKey:   partition,
			JobSetDigest:   jobSetDigest,
			CursorJobID:    current.cursorJobID,
			CompletedCount: current.completedCount,
			FlushedAt:      now.UTC(),
		})
	}
	return due, nil
}

func (t *DataContentCheckpointTracker) Commit(value DataContentPartitionCheckpoint) {
	if t == nil {
		return
	}
	t.progress[value.PartitionKey] = dataContentCheckpointProgress{
		completedCount: value.CompletedCount,
		flushedAt:      value.FlushedAt.UTC(),
	}
}
