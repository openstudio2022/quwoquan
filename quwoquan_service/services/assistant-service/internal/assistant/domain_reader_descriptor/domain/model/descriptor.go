// Package model owns the immutable policy boundary of a domain Reader.
// Runtime context assembly may narrow this boundary, but it may never widen it.
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type ArtifactPolicy string

const (
	ArtifactInlineBounded  ArtifactPolicy = "inline_bounded"
	ArtifactInlineOrStored ArtifactPolicy = "inline_or_artifact"
	ArtifactStoredRequired ArtifactPolicy = "artifact_required"
)

type CitationPolicy string

const (
	CitationNone            CitationPolicy = "none"
	CitationSourceReference CitationPolicy = "source_reference"
	CitationEntityReference CitationPolicy = "entity_reference"
)

type SurfaceKind string

const (
	SurfacePersonal SurfaceKind = "personal"
	SurfaceShared   SurfaceKind = "shared"
	SurfacePublic   SurfaceKind = "public"
)

// Descriptor declares one platform-owned Reader adapter. Every policy-bearing
// field participates in DescriptorDigest so a frozen Run can prove exactly
// which authority, privacy, freshness and artifact boundary it used.
type Descriptor struct {
	DescriptorID        string                                `json:"descriptorId"`
	ResolverRef         string                                `json:"resolverRef"`
	OwnerService        string                                `json:"ownerService"`
	OwnerOperationRefs  []string                              `json:"ownerOperationRefs"`
	InputSchemaRef      string                                `json:"inputSchemaRef"`
	OutputSchemaRef     string                                `json:"outputSchemaRef"`
	ObjectTypeRefs      []string                              `json:"objectTypeRefs"`
	AcceptedSourceKinds []string                              `json:"acceptedSourceKinds"`
	Authority           generated.AssistantContextAuthority   `json:"authority"`
	Sensitivity         generated.AssistantContextSensitivity `json:"sensitivity"`
	MaxFreshnessSeconds int                                   `json:"maxFreshnessSeconds,omitempty"`
	CacheTTLSeconds     int                                   `json:"cacheTtlSeconds,omitempty"`
	SurfaceKinds        []SurfaceKind                         `json:"surfaceKinds"`
	ArtifactPolicy      ArtifactPolicy                        `json:"artifactPolicy"`
	CitationPolicy      CitationPolicy                        `json:"citationPolicy"`
	DescriptorDigest    string                                `json:"descriptorDigest"`
}

type ListSlice struct {
	Items []Descriptor `json:"items"`
}

var (
	ErrInvalidDescriptor  = errors.New("invalid domain reader descriptor")
	ErrDescriptorNotFound = errors.New("domain reader descriptor not found")
)

// NewDescriptor validates and canonicalizes a Reader boundary. A caller may
// provide DescriptorDigest when loading an immutable resource; it must equal
// the digest derived from the normalized policy or construction fails closed.
func NewDescriptor(value Descriptor) (Descriptor, error) {
	value.DescriptorID = strings.TrimSpace(value.DescriptorID)
	value.ResolverRef = strings.TrimSpace(value.ResolverRef)
	value.OwnerService = strings.TrimSpace(value.OwnerService)
	value.InputSchemaRef = strings.TrimSpace(value.InputSchemaRef)
	value.OutputSchemaRef = strings.TrimSpace(value.OutputSchemaRef)
	var valid bool
	value.OwnerOperationRefs, valid = canonicalStrings(value.OwnerOperationRefs)
	if !valid {
		return Descriptor{}, ErrInvalidDescriptor
	}
	value.ObjectTypeRefs, valid = canonicalStrings(value.ObjectTypeRefs)
	if !valid {
		return Descriptor{}, ErrInvalidDescriptor
	}
	value.AcceptedSourceKinds, valid = canonicalStrings(value.AcceptedSourceKinds)
	if !valid {
		return Descriptor{}, ErrInvalidDescriptor
	}
	value.SurfaceKinds, valid = canonicalSurfaceKinds(value.SurfaceKinds)
	if !valid {
		return Descriptor{}, ErrInvalidDescriptor
	}
	providedDigest := strings.TrimSpace(value.DescriptorDigest)
	value.DescriptorDigest = ""
	if value.DescriptorID == "" || value.ResolverRef == "" ||
		value.OwnerService == "" || value.InputSchemaRef == "" ||
		value.OutputSchemaRef == "" || len(value.OwnerOperationRefs) == 0 ||
		len(value.AcceptedSourceKinds) == 0 || value.Authority == "" ||
		value.Sensitivity == "" || len(value.SurfaceKinds) == 0 ||
		value.MaxFreshnessSeconds < 0 || value.CacheTTLSeconds < 0 ||
		!validArtifactPolicy(value.ArtifactPolicy) ||
		!validCitationPolicy(value.CitationPolicy) {
		return Descriptor{}, ErrInvalidDescriptor
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return Descriptor{}, ErrInvalidDescriptor
	}
	digest := sha256.Sum256(raw)
	value.DescriptorDigest = "sha256:" + hex.EncodeToString(digest[:])
	if providedDigest != "" && providedDigest != value.DescriptorDigest {
		return Descriptor{}, ErrInvalidDescriptor
	}
	return value, nil
}

// Clone prevents catalog callers from mutating the policy slices shared by a
// runtime registry or another query response.
func (value Descriptor) Clone() Descriptor {
	value.OwnerOperationRefs = append([]string(nil), value.OwnerOperationRefs...)
	value.ObjectTypeRefs = append([]string(nil), value.ObjectTypeRefs...)
	value.AcceptedSourceKinds = append([]string(nil), value.AcceptedSourceKinds...)
	value.SurfaceKinds = append([]SurfaceKind(nil), value.SurfaceKinds...)
	return value
}

func canonicalStrings(values []string) ([]string, bool) {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			return nil, false
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result, true
}

func canonicalSurfaceKinds(values []SurfaceKind) ([]SurfaceKind, bool) {
	seen := make(map[SurfaceKind]struct{}, len(values))
	result := make([]SurfaceKind, 0, len(values))
	for _, value := range values {
		switch value {
		case SurfacePersonal, SurfaceShared, SurfacePublic:
		default:
			return nil, false
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Slice(result, func(left, right int) bool { return result[left] < result[right] })
	return result, true
}

func validArtifactPolicy(value ArtifactPolicy) bool {
	switch value {
	case ArtifactInlineBounded, ArtifactInlineOrStored, ArtifactStoredRequired:
		return true
	default:
		return false
	}
}

func validCitationPolicy(value CitationPolicy) bool {
	switch value {
	case CitationNone, CitationSourceReference, CitationEntityReference:
		return true
	default:
		return false
	}
}
