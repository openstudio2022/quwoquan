package model

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"math"
	"strings"
	"time"
	"unicode/utf8"
)

const (
	TTL                 = 10 * time.Minute
	MaximumItems        = 20
	MaximumObjectCards  = 20
	MaximumPayloadBytes = 64 * 1024
	// A scope intentionally excludes feedRequestId so an opaque cursor can be
	// authenticated before its sealed attribution is decoded. The same scope can
	// therefore own all eight active RankedFeedWindow values, each at the
	// canonical fifty-page depth.
	MaximumActivePerScope      = 8 * MaximumDepth
	MaximumDepth               = 50
	MaximumFeedRequestIDBytes  = 128
	MaximumPostIDBytes         = 256
	MaximumAttributionBytes    = 64
	MaximumObjectKindBytes     = 64
	MaximumObjectIDBytes       = 256
	MaximumObjectTitleBytes    = 512
	MaximumObjectSubtitleBytes = 1024
	MaximumObjectCoverURLBytes = 4096
	MaximumObjectTagRefs       = 20
	MaximumObjectTagRefBytes   = 256
	MaximumObjectReasonBytes   = 512
	MaximumCursorBytes         = 4096
	MaximumReleaseIDBytes      = 256
	MaximumDigestBytes         = 128
)

var ErrInvalid = errors.New("feed delivery page is invalid")

// ObjectCard is the short-lived public presentation snapshot that was actually
// delivered at an anchor. Replays never call object-card recall again.
type ObjectCard struct {
	ObjectKind  string   `json:"objectKind"`
	ObjectID    string   `json:"objectId"`
	Title       string   `json:"title"`
	Subtitle    string   `json:"subtitle,omitempty"`
	CoverURL    string   `json:"coverUrl,omitempty"`
	TagRefs     []string `json:"tagRefs,omitempty"`
	ReasonText  string   `json:"reasonText,omitempty"`
	RecallPath  string   `json:"recallPath,omitempty"`
	AnchorIndex int      `json:"anchorIndex"`
}

// PostReference preserves the delivery attribution paired with one stable Post
// identity. It deliberately excludes mutable Post presentation fields.
type PostReference struct {
	PostID          string  `json:"postId"`
	QualityScore    float64 `json:"qualityScore,omitempty"`
	RecallPath      string  `json:"recallPath,omitempty"`
	ContentVertical string  `json:"contentVertical,omitempty"`
	SupplySource    string  `json:"supplySource,omitempty"`
}

// Page is an immutable record of one page already delivered by GetFeed. It
// stores stable identities rather than a second Post projection; a replay
// hydrates only these identities under current visibility and never substitutes
// a different candidate.
type Page struct {
	DeliveryPageID string          `json:"deliveryPageId"`
	ScopeHash      string          `json:"scopeHash"`
	FeedRequestID  string          `json:"feedRequestId"`
	PageSize       int             `json:"pageSize"`
	Depth          int             `json:"depth"`
	PreviousPageID string          `json:"previousPageId,omitempty"`
	Items          []PostReference `json:"items"`
	ObjectCards    []ObjectCard    `json:"objectCards,omitempty"`
	OutboundCursor string          `json:"outboundCursor,omitempty"`
	ReleaseID      string          `json:"releaseId,omitempty"`
	ManifestDigest string          `json:"manifestDigest,omitempty"`
	PolicyDigest   string          `json:"policyDigest,omitempty"`
	CreatedAt      time.Time       `json:"createdAt"`
	ExpiresAt      time.Time       `json:"expiresAt"`
}

func NewID() (string, error) {
	raw := make([]byte, 16)
	if _, err := rand.Read(raw); err != nil {
		return "", fmt.Errorf("generate feed delivery page id: %w", err)
	}
	return "fdp_" + base64.RawURLEncoding.EncodeToString(raw), nil
}

// ScopeHash keeps actor/session data out of Redis keys while binding the exact
// length-prefixed request scope, including the normalized page size.
func ScopeHash(scope string) string {
	digest := sha256.Sum256([]byte(scope))
	return hex.EncodeToString(digest[:])
}

func ValidIdentity(scopeHash, deliveryPageID string) bool {
	return validHash(strings.TrimSpace(scopeHash)) &&
		validID(strings.TrimSpace(deliveryPageID), "fdp_")
}

func (p Page) Validate(now time.Time) error {
	if !validID(p.DeliveryPageID, "fdp_") ||
		!validHash(p.ScopeHash) || !validBoundedText(p.FeedRequestID, MaximumFeedRequestIDBytes, true) ||
		p.PageSize <= 0 || p.PageSize > MaximumItems || p.Depth < 0 ||
		p.Depth > MaximumDepth || len(p.Items) == 0 ||
		len(p.Items) > p.PageSize || len(p.ObjectCards) > MaximumObjectCards ||
		p.CreatedAt.IsZero() || p.ExpiresAt.IsZero() ||
		!p.ExpiresAt.Equal(p.CreatedAt.Add(TTL)) ||
		!p.ExpiresAt.After(now.UTC()) {
		return ErrInvalid
	}
	if (strings.TrimSpace(p.ReleaseID) == "") != (strings.TrimSpace(p.ManifestDigest) == "") {
		return ErrInvalid
	}
	if p.PreviousPageID != "" && !validID(p.PreviousPageID, "fdp_") {
		return ErrInvalid
	}
	if (p.Depth == 0) != (strings.TrimSpace(p.PreviousPageID) == "") ||
		!validBoundedText(p.OutboundCursor, MaximumCursorBytes, true) ||
		!validBoundedText(p.ReleaseID, MaximumReleaseIDBytes, false) ||
		!validBoundedText(p.ManifestDigest, MaximumDigestBytes, false) ||
		!validBoundedText(p.PolicyDigest, MaximumDigestBytes, false) ||
		(strings.TrimSpace(p.PolicyDigest) != "" && !validSHA256Digest(p.PolicyDigest)) {
		return ErrInvalid
	}
	seen := make(map[string]struct{}, len(p.Items))
	for _, item := range p.Items {
		postID := strings.TrimSpace(item.PostID)
		if !validBoundedText(postID, MaximumPostIDBytes, true) ||
			math.IsNaN(item.QualityScore) || math.IsInf(item.QualityScore, 0) ||
			!validBoundedText(item.RecallPath, MaximumAttributionBytes, false) ||
			!validBoundedText(item.ContentVertical, MaximumAttributionBytes, false) ||
			!validBoundedText(item.SupplySource, MaximumAttributionBytes, false) {
			return ErrInvalid
		}
		if _, duplicate := seen[postID]; duplicate {
			return ErrInvalid
		}
		seen[postID] = struct{}{}
	}
	for _, card := range p.ObjectCards {
		if !validBoundedText(card.ObjectKind, MaximumObjectKindBytes, true) ||
			!validBoundedText(card.ObjectID, MaximumObjectIDBytes, true) ||
			!validBoundedText(card.Title, MaximumObjectTitleBytes, true) ||
			!validBoundedText(card.Subtitle, MaximumObjectSubtitleBytes, false) ||
			!validBoundedText(card.CoverURL, MaximumObjectCoverURLBytes, false) ||
			!validBoundedText(card.ReasonText, MaximumObjectReasonBytes, false) ||
			!validBoundedText(card.RecallPath, MaximumAttributionBytes, false) ||
			len(card.TagRefs) > MaximumObjectTagRefs ||
			card.AnchorIndex < 0 || card.AnchorIndex > len(p.Items) {
			return ErrInvalid
		}
		for _, tagRef := range card.TagRefs {
			if !validBoundedText(tagRef, MaximumObjectTagRefBytes, true) {
				return ErrInvalid
			}
		}
	}
	return nil
}

func validBoundedText(value string, maximumBytes int, required bool) bool {
	trimmed := strings.TrimSpace(value)
	if required && trimmed == "" {
		return false
	}
	return utf8.ValidString(value) && len(value) <= maximumBytes
}

func validID(value, prefix string) bool {
	value = strings.TrimSpace(value)
	if !strings.HasPrefix(value, prefix) {
		return false
	}
	raw, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(value, prefix))
	return err == nil && len(raw) == 16
}

func validHash(value string) bool {
	if len(value) != sha256.Size*2 {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256.Size
}

func validSHA256Digest(value string) bool {
	const prefix = "sha256:"
	if !strings.HasPrefix(value, prefix) {
		return false
	}
	return validHash(strings.TrimPrefix(value, prefix))
}
