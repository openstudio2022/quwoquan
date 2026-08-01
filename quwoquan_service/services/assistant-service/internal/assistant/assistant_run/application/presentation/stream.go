package presentation

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type PatchOperation string

const (
	PatchAdd     PatchOperation = "add"
	PatchReplace PatchOperation = "replace"
	PatchRemove  PatchOperation = "remove"
)

type NodePatch struct {
	Operation PatchOperation
	NodeID    string
	Node      *Node
}

type StreamEvent struct {
	Type         generated.AssistantStreamEventType
	BaseRevision int64
	Revision     int64
	Document     *Document
	Patches      []NodePatch
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
	if p.committed || event.BaseRevision != p.revision || event.Revision != p.revision+1 {
		return ErrPresentationRevision
	}
	switch event.Type {
	case generated.AssistantStreamEventTypePresentationSnapshot:
		if p.revision != 0 || event.Document == nil || event.Document.Revision != event.Revision {
			return ErrPresentationRevision
		}
		p.document = cloneDocument(*event.Document)
	case generated.AssistantStreamEventTypePresentationPatch:
		if p.revision == 0 || event.Document != nil || len(event.Patches) == 0 {
			return ErrPresentationRevision
		}
		nodes, err := applyNodePatches(p.document, event.Patches)
		if err != nil {
			return err
		}
		p.document.Nodes = nodes
		p.document.Revision = event.Revision
	case generated.AssistantStreamEventTypePresentationCommit:
		if p.revision == 0 || event.Document != nil || len(event.Patches) != 0 {
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

func applyNodePatches(document Document, patches []NodePatch) ([]Node, error) {
	nodes := cloneNodes(document.Nodes)
	for _, patch := range patches {
		index := -1
		for candidate := range nodes {
			if nodes[candidate].NodeID == patch.NodeID {
				index = candidate
				break
			}
		}
		switch patch.Operation {
		case PatchAdd:
			if index >= 0 || patch.Node == nil || patch.Node.NodeID != patch.NodeID {
				return nil, ErrPresentationRevision
			}
			nodes = append(nodes, cloneNodes([]Node{*patch.Node})[0])
		case PatchReplace:
			if index < 0 || patch.Node == nil || patch.Node.NodeID != patch.NodeID {
				return nil, ErrPresentationRevision
			}
			nodes[index] = cloneNodes([]Node{*patch.Node})[0]
		case PatchRemove:
			if index < 0 || patch.Node != nil || patch.NodeID == document.RootNodeID || hasChild(nodes, patch.NodeID) {
				return nil, ErrPresentationRevision
			}
			nodes = append(nodes[:index], nodes[index+1:]...)
		default:
			return nil, ErrPresentationRevision
		}
	}
	if err := validateResolvedTree(document.RootNodeID, nodes); err != nil {
		return nil, err
	}
	return nodes, nil
}

func validateResolvedTree(rootID string, nodes []Node) error {
	byID := make(map[string]Node, len(nodes))
	for _, node := range nodes {
		if strings.TrimSpace(node.NodeID) == "" || byID[node.NodeID].NodeID != "" {
			return ErrPresentationRevision
		}
		byID[node.NodeID] = node
	}
	root, ok := byID[rootID]
	if !ok || root.ParentNodeID != "" {
		return ErrPresentationRevision
	}
	for _, node := range nodes {
		if node.NodeID == rootID {
			continue
		}
		if _, ok := byID[node.ParentNodeID]; !ok {
			return ErrPresentationRevision
		}
		if depth, cyclic := nodeDepth(node, byID); cyclic || depth > maxTemplateDepth {
			return ErrPresentationRevision
		}
	}
	return nil
}

func hasChild(nodes []Node, nodeID string) bool {
	for _, node := range nodes {
		if node.ParentNodeID == nodeID {
			return true
		}
	}
	return false
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
