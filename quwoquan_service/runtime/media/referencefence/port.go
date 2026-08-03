// Package referencefence defines the cross-aggregate transaction participant
// used when another object creates a durable reference to a MediaAsset.
package referencefence

import (
	"context"
	"errors"
)

var (
	ErrDeletionInProgress   = errors.New("media asset deletion is in progress")
	ErrReferenceUnavailable = errors.New("media asset is unavailable for reference")
)

type Reference struct {
	AssetID string
	OwnerID string
}

// Fence is the MediaAsset-owned transaction participant used by aggregate
// stores that create durable references to ready assets.
type Fence interface {
	AllowReferences(context.Context, []Reference) error
}
