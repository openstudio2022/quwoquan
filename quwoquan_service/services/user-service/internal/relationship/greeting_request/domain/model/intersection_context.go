package model

import (
	"encoding/json"
	"strings"
	"time"
)

// GreetingIntersectionRef 是客户端可声明的最小意图引用，不含展示事实。
type GreetingIntersectionRef struct {
	IntersectionID string `json:"intersectionId"`
	EvidenceID     string `json:"evidenceId"`
	SourceRef      string `json:"sourceRef"`
	ObjectTypeRef  string `json:"objectTypeRef"`
	ObjectID       string `json:"objectId"`
}

func (r GreetingIntersectionRef) Normalized() GreetingIntersectionRef {
	return GreetingIntersectionRef{
		IntersectionID: strings.TrimSpace(r.IntersectionID),
		EvidenceID:     strings.TrimSpace(r.EvidenceID),
		SourceRef:      strings.TrimSpace(r.SourceRef),
		ObjectTypeRef:  strings.TrimSpace(r.ObjectTypeRef),
		ObjectID:       strings.TrimSpace(r.ObjectID),
	}
}

func (r GreetingIntersectionRef) Complete() bool {
	r = r.Normalized()
	return r.IntersectionID != "" && r.EvidenceID != "" && r.SourceRef != "" &&
		r.ObjectTypeRef != "" && r.ObjectID != ""
}

// GreetingIntersectionSnapshot 是服务端重解析后冻结的唯一可见破冰依据。
type GreetingIntersectionSnapshot struct {
	IntersectionID string    `json:"intersectionId"`
	EvidenceID     string    `json:"evidenceId"`
	SourceRef      string    `json:"sourceRef"`
	ObjectTypeRef  string    `json:"objectTypeRef"`
	ObjectID       string    `json:"objectId"`
	PrimaryText    string    `json:"primaryText"`
	Dimension      string    `json:"dimension,omitempty"`
	ResolvedAt     time.Time `json:"resolvedAt"`
}

func EncodeIntersectionRef(ref *GreetingIntersectionRef) json.RawMessage {
	if ref == nil || !ref.Complete() {
		return nil
	}
	normalized := ref.Normalized()
	payload, err := json.Marshal(normalized)
	if err != nil {
		return nil
	}
	return payload
}

func EncodeIntersectionSnapshot(snapshot *GreetingIntersectionSnapshot) json.RawMessage {
	if snapshot == nil || strings.TrimSpace(snapshot.PrimaryText) == "" {
		return nil
	}
	payload, err := json.Marshal(snapshot)
	if err != nil {
		return nil
	}
	return payload
}

func DecodeIntersectionSnapshot(raw json.RawMessage) *GreetingIntersectionSnapshot {
	if len(raw) == 0 || string(raw) == "null" {
		return nil
	}
	var snapshot GreetingIntersectionSnapshot
	if err := json.Unmarshal(raw, &snapshot); err != nil || strings.TrimSpace(snapshot.PrimaryText) == "" {
		return nil
	}
	return &snapshot
}
