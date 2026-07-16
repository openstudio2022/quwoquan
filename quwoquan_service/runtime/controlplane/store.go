package controlplane

import (
	"encoding/json"
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
