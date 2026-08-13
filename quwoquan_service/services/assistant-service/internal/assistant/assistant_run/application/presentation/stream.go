package presentation

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type StreamEvent struct {
	Type         generated.AssistantStreamEventType
	BaseRevision int64
	Revision     int64
	Document     *Document
}

type StreamProjection struct {
	document  Document
	revision  int64
	committed bool
	digests   map[int64]string
}

var ErrPresentationRevision = errors.New("assistant presentation revision conflict")

func NewStreamProjection() *StreamProjection {
	return &StreamProjection{digests: map[int64]string{}}
}

func (p *StreamProjection) Apply(event StreamEvent) error {
	if p == nil || event.Revision <= 0 {
		return ErrPresentationRevision
	}
	digest, err := eventDigest(event)
	if err != nil {
		return err
	}
	if existing, ok := p.digests[event.Revision]; ok {
		if existing == digest {
			return nil
		}
		return ErrPresentationRevision
	}
	replacesCommittedDocument :=
		event.Type == generated.AssistantStreamEventTypePresentationSnapshot &&
			p.committed
	if (!replacesCommittedDocument && p.committed) ||
		event.BaseRevision != p.revision ||
		event.Revision != p.revision+1 {
		return ErrPresentationRevision
	}
	switch event.Type {
	case generated.AssistantStreamEventTypePresentationSnapshot:
		if (!replacesCommittedDocument && p.revision != 0) ||
			event.Document == nil ||
			event.Document.Revision != event.Revision ||
			!event.Document.CommittedAt.IsZero() {
			return ErrPresentationRevision
		}
		p.document = cloneDocument(*event.Document)
		p.committed = false
	case generated.AssistantStreamEventTypePresentationCommit:
		if p.revision == 0 || event.Document != nil {
			return ErrPresentationRevision
		}
		p.document.Revision = event.Revision
		p.committed = true
	default:
		return ErrPresentationRevision
	}
	p.revision = event.Revision
	p.digests[event.Revision] = digest
	return nil
}

func (p *StreamProjection) Snapshot() (Document, bool) {
	if p == nil || p.revision == 0 {
		return Document{}, false
	}
	return cloneDocument(p.document), p.committed
}

func eventDigest(event StreamEvent) (string, error) {
	raw, err := json.Marshal(event)
	if err != nil {
		return "", fmt.Errorf("presentation event digest: %w", err)
	}
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:]), nil
}

func cloneDocument(value Document) Document {
	value.Nodes = cloneNodes(value.Nodes)
	return value
}
