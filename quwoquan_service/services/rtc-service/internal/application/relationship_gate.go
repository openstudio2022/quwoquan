package application

import "context"

type RelationshipCapability struct {
	IsMutual    bool
	IsBlocked   bool
	IsBlockedBy bool
}

type RelationshipGate interface {
	GetCapability(ctx context.Context, viewerID, targetID string) (RelationshipCapability, error)
}

type denyRelationshipGate struct{}

func (denyRelationshipGate) GetCapability(context.Context, string, string) (RelationshipCapability, error) {
	return RelationshipCapability{}, nil
}

func DenyRelationshipGate() RelationshipGate { return denyRelationshipGate{} }

type allowRelationshipGate struct{}

func (allowRelationshipGate) GetCapability(context.Context, string, string) (RelationshipCapability, error) {
	return RelationshipCapability{IsMutual: true}, nil
}

func AllowRelationshipGateForTest() RelationshipGate { return allowRelationshipGate{} }
