// Package testsupport provides local-contract-only control-plane adapters.
// Production composition must not import this package.
package testsupport

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"quwoquan_service/runtime/controlplane"
)

type Document = controlplane.Document
type WorkflowTransition = controlplane.WorkflowTransition
type WorkflowState = controlplane.WorkflowState
type ApprovalDecision = controlplane.ApprovalDecision
type AuditEvent = controlplane.AuditEvent
type MutationReceipt = controlplane.MutationReceipt
type MutationOutboxEvent = controlplane.MutationOutboxEvent

type FileState struct {
	Documents        map[string]map[string]Document `json:"documents"`
	Workflows        map[string]WorkflowState       `json:"workflows"`
	Approvals        map[string][]ApprovalDecision  `json:"approvals"`
	Audits           []AuditEvent                   `json:"audits"`
	MutationReceipts map[string]MutationReceipt     `json:"mutationReceipts"`
	MutationOutbox   []MutationOutboxEvent          `json:"mutationOutbox"`
}

type FileStore struct {
	path string
	mu   sync.Mutex
}

var _ controlplane.StateStore = (*FileStore)(nil)
var _ controlplane.AtomicMutationStore = (*FileStore)(nil)

func NewFileStore(path string) *FileStore {
	return &FileStore{path: path}
}

func (s *FileStore) GetDocument(namespace, id string) (Document, bool, error) {
	state, err := s.read()
	if err != nil {
		return nil, false, err
	}
	items := state.Documents[namespace]
	if items == nil {
		return nil, false, nil
	}
	doc, ok := items[id]
	if !ok {
		return nil, false, nil
	}
	return cloneDocument(doc), true, nil
}

func (s *FileStore) PutDocument(namespace, id string, doc Document) error {
	if namespace == "" || id == "" {
		return errors.New("namespace and id are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.readLocked()
	if err != nil {
		return err
	}
	if state.Documents == nil {
		state.Documents = map[string]map[string]Document{}
	}
	if state.Documents[namespace] == nil {
		state.Documents[namespace] = map[string]Document{}
	}
	state.Documents[namespace][id] = cloneDocument(doc)
	return s.writeLocked(state)
}

// PutDocumentIfAbsent atomically appends one immutable document. It returns the
// canonical stored document so idempotent retries observe the first write and
// can never overwrite an append-only fact.
func (s *FileStore) PutDocumentIfAbsent(namespace, id string, doc Document) (Document, bool, error) {
	if namespace == "" || id == "" {
		return nil, false, errors.New("namespace and id are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.readLocked()
	if err != nil {
		return nil, false, err
	}
	if state.Documents == nil {
		state.Documents = map[string]map[string]Document{}
	}
	if state.Documents[namespace] == nil {
		state.Documents[namespace] = map[string]Document{}
	}
	if existing, ok := state.Documents[namespace][id]; ok {
		return cloneDocument(existing), false, nil
	}
	canonical := cloneDocument(doc)
	state.Documents[namespace][id] = canonical
	if err := s.writeLocked(state); err != nil {
		return nil, false, err
	}
	return cloneDocument(canonical), true, nil
}

func (s *FileStore) DeleteDocument(namespace, id string) error {
	if namespace == "" || id == "" {
		return errors.New("namespace and id are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.readLocked()
	if err != nil {
		return err
	}
	items := state.Documents[namespace]
	if items == nil {
		return nil
	}
	delete(items, id)
	if len(items) == 0 {
		delete(state.Documents, namespace)
	}
	return s.writeLocked(state)
}

func (s *FileStore) ListDocuments(namespace string) ([]Document, error) {
	state, err := s.read()
	if err != nil {
		return nil, err
	}
	items := state.Documents[namespace]
	out := make([]Document, 0, len(items))
	for _, item := range items {
		out = append(out, cloneDocument(item))
	}
	sort.Slice(out, func(i, j int) bool {
		return documentID(out[i]) < documentID(out[j])
	})
	return out, nil
}

func (s *FileStore) UpsertWorkflow(workflow WorkflowState) error {
	if workflow.ObjectType == "" || workflow.ObjectID == "" {
		return errors.New("workflow object type and id are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.readLocked()
	if err != nil {
		return err
	}
	if state.Workflows == nil {
		state.Workflows = map[string]WorkflowState{}
	}
	if workflow.UpdatedAt == "" {
		workflow.UpdatedAt = nowRFC3339()
	}
	state.Workflows[workflowKey(workflow.ObjectType, workflow.ObjectID)] = workflow
	return s.writeLocked(state)
}

func (s *FileStore) GetWorkflow(objectType, objectID string) (WorkflowState, bool, error) {
	state, err := s.read()
	if err != nil {
		return WorkflowState{}, false, err
	}
	workflow, ok := state.Workflows[workflowKey(objectType, objectID)]
	return workflow, ok, nil
}

func (s *FileStore) ListWorkflows() ([]WorkflowState, error) {
	state, err := s.read()
	if err != nil {
		return nil, err
	}
	out := make([]WorkflowState, 0, len(state.Workflows))
	for _, item := range state.Workflows {
		out = append(out, item)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].ObjectType == out[j].ObjectType {
			return out[i].ObjectID < out[j].ObjectID
		}
		return out[i].ObjectType < out[j].ObjectType
	})
	return out, nil
}

func (s *FileStore) AppendApproval(item ApprovalDecision) error {
	if item.ObjectType == "" || item.ObjectID == "" {
		return errors.New("approval object type and id are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.readLocked()
	if err != nil {
		return err
	}
	if state.Approvals == nil {
		state.Approvals = map[string][]ApprovalDecision{}
	}
	if item.At == "" {
		item.At = nowRFC3339()
	}
	key := workflowKey(item.ObjectType, item.ObjectID)
	state.Approvals[key] = append(state.Approvals[key], item)
	return s.writeLocked(state)
}

func (s *FileStore) ListApprovals(objectType, objectID string) ([]ApprovalDecision, error) {
	state, err := s.read()
	if err != nil {
		return nil, err
	}
	out := append([]ApprovalDecision(nil), state.Approvals[workflowKey(objectType, objectID)]...)
	sort.Slice(out, func(i, j int) bool {
		return out[i].At < out[j].At
	})
	return out, nil
}

func (s *FileStore) ListAllApprovals() ([]ApprovalDecision, error) {
	state, err := s.read()
	if err != nil {
		return nil, err
	}
	out := make([]ApprovalDecision, 0)
	for _, items := range state.Approvals {
		out = append(out, items...)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].At == out[j].At {
			if out[i].ObjectType == out[j].ObjectType {
				return out[i].ObjectID < out[j].ObjectID
			}
			return out[i].ObjectType < out[j].ObjectType
		}
		return out[i].At > out[j].At
	})
	return out, nil
}

func (s *FileStore) AppendAudit(event AuditEvent) error {
	if event.AuditID == "" || event.ObjectType == "" || event.ObjectID == "" {
		return errors.New("audit id, object type and object id are required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()

	state, err := s.readLocked()
	if err != nil {
		return err
	}
	if event.At == "" {
		event.At = nowRFC3339()
	}
	state.Audits = append(state.Audits, event)
	return s.writeLocked(state)
}

func (s *FileStore) ListAudits() ([]AuditEvent, error) {
	state, err := s.read()
	if err != nil {
		return nil, err
	}
	out := append([]AuditEvent(nil), state.Audits...)
	sort.Slice(out, func(i, j int) bool {
		return out[i].At > out[j].At
	})
	return out, nil
}

func (s *FileStore) CommitApprovedMutation(
	mutation controlplane.ApprovedMutation,
) (MutationReceipt, error) {
	if err := controlplane.ValidateApprovedMutation(mutation); err != nil {
		return MutationReceipt{}, err
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	state, err := s.readLocked()
	if err != nil {
		return MutationReceipt{}, err
	}
	key := mutationReceiptKey(
		mutation.ObjectType,
		mutation.ObjectID,
		mutation.IdempotencyKey,
	)
	if existing, ok := state.MutationReceipts[key]; ok {
		if existing.Intent != mutation.Intent ||
			existing.PayloadDigest != mutation.PayloadDigest {
			return MutationReceipt{}, controlplane.ErrMutationIdempotencyConflict
		}
		existing.Replayed = true
		return existing, nil
	}
	actors := map[string]struct{}{}
	for _, approval := range state.Approvals[workflowKey(mutation.ObjectType, mutation.ObjectID)] {
		actor := strings.TrimSpace(approval.Actor)
		if approval.Decision == mutation.ApprovalDecision &&
			approval.PayloadDigest == mutation.PayloadDigest &&
			actor != "" && actor != "unverified" {
			actors[actor] = struct{}{}
		}
	}
	if len(actors) < 2 {
		return MutationReceipt{}, controlplane.ErrDualApprovalRequired
	}
	if state.Documents[mutation.Namespace] == nil {
		state.Documents[mutation.Namespace] = map[string]Document{}
	}
	committedAt := time.Now().UTC().Format(time.RFC3339Nano)
	if mutation.Workflow.UpdatedAt == "" {
		mutation.Workflow.UpdatedAt = committedAt
	}
	if mutation.Audit.At == "" {
		mutation.Audit.At = committedAt
	}
	state.Documents[mutation.Namespace][mutation.ObjectID] = cloneDocument(mutation.Document)
	state.Workflows[workflowKey(mutation.ObjectType, mutation.ObjectID)] = mutation.Workflow
	state.Audits = append(state.Audits, mutation.Audit)
	state.MutationOutbox = append(state.MutationOutbox, mutation.OutboxEvents...)
	receipt := MutationReceipt{
		ObjectType:     mutation.ObjectType,
		ObjectID:       mutation.ObjectID,
		Intent:         mutation.Intent,
		PayloadDigest:  mutation.PayloadDigest,
		IdempotencyKey: mutation.IdempotencyKey,
		CommittedAt:    committedAt,
	}
	state.MutationReceipts[key] = receipt
	if err := s.writeLocked(state); err != nil {
		return MutationReceipt{}, err
	}
	return receipt, nil
}

func (s *FileStore) GetMutationReceipt(
	objectType string,
	objectID string,
	idempotencyKey string,
) (MutationReceipt, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	state, err := s.readLocked()
	if err != nil {
		return MutationReceipt{}, false, err
	}
	receipt, ok := state.MutationReceipts[mutationReceiptKey(
		objectType,
		objectID,
		idempotencyKey,
	)]
	return receipt, ok, nil
}

func (s *FileStore) read() (FileState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.readLocked()
}

func (s *FileStore) readLocked() (FileState, error) {
	if err := os.MkdirAll(filepath.Dir(s.path), 0o755); err != nil {
		return FileState{}, err
	}
	data, err := os.ReadFile(s.path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return FileState{
				Documents:        map[string]map[string]Document{},
				Workflows:        map[string]WorkflowState{},
				Approvals:        map[string][]ApprovalDecision{},
				Audits:           []AuditEvent{},
				MutationReceipts: map[string]MutationReceipt{},
				MutationOutbox:   []MutationOutboxEvent{},
			}, nil
		}
		return FileState{}, err
	}
	var state FileState
	if err := json.Unmarshal(data, &state); err != nil {
		return FileState{}, err
	}
	if state.Documents == nil {
		state.Documents = map[string]map[string]Document{}
	}
	if state.Workflows == nil {
		state.Workflows = map[string]WorkflowState{}
	}
	if state.Approvals == nil {
		state.Approvals = map[string][]ApprovalDecision{}
	}
	if state.Audits == nil {
		state.Audits = []AuditEvent{}
	}
	if state.MutationReceipts == nil {
		state.MutationReceipts = map[string]MutationReceipt{}
	}
	if state.MutationOutbox == nil {
		state.MutationOutbox = []MutationOutboxEvent{}
	}
	return state, nil
}

func (s *FileStore) writeLocked(state FileState) error {
	data, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.path, data, 0o644)
}

func workflowKey(objectType, objectID string) string {
	return objectType + ":" + objectID
}

func mutationReceiptKey(objectType, objectID, idempotencyKey string) string {
	return objectType + ":" + objectID + ":" + idempotencyKey
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}

func cloneDocument(in Document) Document {
	if in == nil {
		return nil
	}
	data, _ := json.Marshal(in)
	var out Document
	_ = json.Unmarshal(data, &out)
	return out
}

func documentID(doc Document) string {
	if id, ok := doc["id"].(string); ok {
		return id
	}
	if id, ok := doc["key"].(string); ok {
		return id
	}
	return ""
}
