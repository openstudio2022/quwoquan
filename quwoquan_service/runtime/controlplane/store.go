package controlplane

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"
)

type Document map[string]any

type WorkflowTransition struct {
	From   string `json:"from"`
	To     string `json:"to"`
	Action string `json:"action"`
	Actor  string `json:"actor"`
	Reason string `json:"reason,omitempty"`
	At     string `json:"at"`
}

type WorkflowState struct {
	ObjectType string               `json:"objectType"`
	ObjectID   string               `json:"objectId"`
	WorkflowID string               `json:"workflowId"`
	State      string               `json:"state"`
	History    []WorkflowTransition `json:"history"`
	UpdatedAt  string               `json:"updatedAt"`
}

type ApprovalDecision struct {
	ObjectType string `json:"objectType"`
	ObjectID   string `json:"objectId"`
	Mode       string `json:"mode"`
	Actor      string `json:"actor"`
	Decision   string `json:"decision"`
	Comment    string `json:"comment,omitempty"`
	At         string `json:"at"`
}

type AuditEvent struct {
	AuditID      string         `json:"auditId"`
	ObjectType   string         `json:"objectType"`
	ObjectID     string         `json:"objectId"`
	Action       string         `json:"action"`
	DangerLevel  string         `json:"dangerLevel"`
	Actor        string         `json:"actor"`
	Environment  string         `json:"environment"`
	RequestID    string         `json:"requestId"`
	TraceID      string         `json:"traceId"`
	WorkflowRef  string         `json:"workflowRef,omitempty"`
	RollbackToken string        `json:"rollbackToken,omitempty"`
	Before       map[string]any `json:"before,omitempty"`
	After        map[string]any `json:"after,omitempty"`
	Metadata     map[string]any `json:"metadata,omitempty"`
	At           string         `json:"at"`
}

type FileState struct {
	Documents map[string]map[string]Document   `json:"documents"`
	Workflows map[string]WorkflowState         `json:"workflows"`
	Approvals map[string][]ApprovalDecision    `json:"approvals"`
	Audits    []AuditEvent                     `json:"audits"`
}

type FileStore struct {
	path string
	mu   sync.Mutex
}

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
				Documents: map[string]map[string]Document{},
				Workflows: map[string]WorkflowState{},
				Approvals: map[string][]ApprovalDecision{},
				Audits:    []AuditEvent{},
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
