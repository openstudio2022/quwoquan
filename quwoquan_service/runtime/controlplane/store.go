package controlplane

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
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
	ObjectType    string `json:"objectType"`
	ObjectID      string `json:"objectId"`
	Mode          string `json:"mode"`
	Actor         string `json:"actor"`
	Decision      string `json:"decision"`
	PayloadDigest string `json:"payloadDigest,omitempty"`
	Comment       string `json:"comment,omitempty"`
	At            string `json:"at"`
}

type AuditEvent struct {
	AuditID       string         `json:"auditId"`
	ObjectType    string         `json:"objectType"`
	ObjectID      string         `json:"objectId"`
	Action        string         `json:"action"`
	DangerLevel   string         `json:"dangerLevel"`
	Actor         string         `json:"actor"`
	Environment   string         `json:"environment"`
	RequestID     string         `json:"requestId"`
	TraceID       string         `json:"traceId"`
	WorkflowRef   string         `json:"workflowRef,omitempty"`
	RollbackToken string         `json:"rollbackToken,omitempty"`
	Before        map[string]any `json:"before,omitempty"`
	After         map[string]any `json:"after,omitempty"`
	Metadata      map[string]any `json:"metadata,omitempty"`
	At            string         `json:"at"`
}

var (
	ErrDualApprovalRequired        = errors.New("two distinct verified approvals are required")
	ErrMutationIdempotencyConflict = errors.New("control-plane mutation idempotency conflict")
)

type MutationOutboxEvent struct {
	EventID       string         `json:"eventId"`
	EventType     string         `json:"eventType"`
	AggregateType string         `json:"aggregateType"`
	AggregateID   string         `json:"aggregateId"`
	Payload       map[string]any `json:"payload"`
	OccurredAt    string         `json:"occurredAt"`
}

type ApprovedMutation struct {
	Namespace        string                `json:"namespace"`
	ObjectType       string                `json:"objectType"`
	ObjectID         string                `json:"objectId"`
	Intent           string                `json:"intent"`
	ApprovalDecision string                `json:"approvalDecision"`
	PayloadDigest    string                `json:"payloadDigest"`
	IdempotencyKey   string                `json:"idempotencyKey"`
	Document         Document              `json:"document"`
	Workflow         WorkflowState         `json:"workflow"`
	Audit            AuditEvent            `json:"audit"`
	OutboxEvents     []MutationOutboxEvent `json:"outboxEvents"`
}

// Mutation is the atomic boundary for an ordinary control-plane state change.
// It commits document, workflow, audit, outbox and idempotency receipt together;
// dangerous operations use ApprovedMutation to add the dual-approval invariant.
type Mutation struct {
	Namespace      string                `json:"namespace"`
	ObjectType     string                `json:"objectType"`
	ObjectID       string                `json:"objectId"`
	Intent         string                `json:"intent"`
	PayloadDigest  string                `json:"payloadDigest"`
	IdempotencyKey string                `json:"idempotencyKey"`
	Document       Document              `json:"document"`
	Workflow       WorkflowState         `json:"workflow"`
	Audit          AuditEvent            `json:"audit"`
	OutboxEvents   []MutationOutboxEvent `json:"outboxEvents"`
}

type MutationReceipt struct {
	ObjectType     string `json:"objectType"`
	ObjectID       string `json:"objectId"`
	Intent         string `json:"intent"`
	PayloadDigest  string `json:"payloadDigest"`
	IdempotencyKey string `json:"idempotencyKey"`
	CommittedAt    string `json:"committedAt"`
	Replayed       bool   `json:"replayed"`
}

// AtomicMutationStore is the production boundary for dangerous control-plane
// mutations. Approval verification, document/workflow state, audit, outbox and
// idempotency receipt must commit in one database transaction.
type AtomicMutationStore interface {
	CommitMutation(Mutation) (MutationReceipt, error)
	CommitApprovedMutation(ApprovedMutation) (MutationReceipt, error)
	GetMutationReceipt(
		objectType string,
		objectID string,
		idempotencyKey string,
	) (MutationReceipt, bool, error)
}

func ValidateMutation(mutation Mutation) error {
	for name, value := range map[string]string{
		"namespace":      mutation.Namespace,
		"objectType":     mutation.ObjectType,
		"objectId":       mutation.ObjectID,
		"intent":         mutation.Intent,
		"payloadDigest":  mutation.PayloadDigest,
		"idempotencyKey": mutation.IdempotencyKey,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("mutation %s is required", name)
		}
	}
	if len(strings.TrimSpace(mutation.PayloadDigest)) != 64 {
		return errors.New("mutation payload digest must be sha256")
	}
	if mutation.Document == nil ||
		mutation.Workflow.ObjectType != mutation.ObjectType ||
		mutation.Workflow.ObjectID != mutation.ObjectID ||
		mutation.Audit.ObjectType != mutation.ObjectType ||
		mutation.Audit.ObjectID != mutation.ObjectID {
		return errors.New("mutation state, workflow and audit must share object identity")
	}
	if mutation.Audit.AuditID == "" {
		return errors.New("mutation audit id is required")
	}
	if len(mutation.OutboxEvents) == 0 {
		return errors.New("mutation requires at least one transactional outbox event")
	}
	for _, event := range mutation.OutboxEvents {
		if event.EventID == "" || event.EventType == "" ||
			event.AggregateType == "" || event.AggregateID == "" ||
			event.Payload == nil {
			return errors.New("mutation outbox event is incomplete")
		}
	}
	return nil
}

func ValidateApprovedMutation(mutation ApprovedMutation) error {
	if err := ValidateMutation(Mutation{
		Namespace: mutation.Namespace, ObjectType: mutation.ObjectType,
		ObjectID: mutation.ObjectID, Intent: mutation.Intent,
		PayloadDigest: mutation.PayloadDigest, IdempotencyKey: mutation.IdempotencyKey,
		Document: mutation.Document, Workflow: mutation.Workflow,
		Audit: mutation.Audit, OutboxEvents: mutation.OutboxEvents,
	}); err != nil {
		return err
	}
	for name, value := range map[string]string{
		"approvalDecision": mutation.ApprovalDecision,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("approved mutation %s is required", name)
		}
	}
	return nil
}

// StateStore 是控制面状态的持久化边界。生产装配必须使用 PostgreSQL；
// local-contract 文件适配器位于 testsupport 子包，不能进入 runtime composition。
type StateStore interface {
	GetDocument(namespace, id string) (Document, bool, error)
	PutDocument(namespace, id string, doc Document) error
	PutDocumentIfAbsent(namespace, id string, doc Document) (Document, bool, error)
	DeleteDocument(namespace, id string) error
	ListDocuments(namespace string) ([]Document, error)
	UpsertWorkflow(workflow WorkflowState) error
	GetWorkflow(objectType, objectID string) (WorkflowState, bool, error)
	ListWorkflows() ([]WorkflowState, error)
	AppendApproval(item ApprovalDecision) error
	ListApprovals(objectType, objectID string) ([]ApprovalDecision, error)
	ListAllApprovals() ([]ApprovalDecision, error)
	AppendAudit(event AuditEvent) error
	ListAudits() ([]AuditEvent, error)
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

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}
