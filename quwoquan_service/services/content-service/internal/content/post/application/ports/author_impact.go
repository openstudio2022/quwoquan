package ports

import (
	"crypto/sha1"
	"encoding/hex"
	"strings"
)

// StableImpactID derives a stable drill-down anchor from the AuthorImpactItem
// aggregation key (authorId|helpType|action|dimension|tagRef|source).
func StableImpactID(authorID, helpType, action, dimension, tagRef, source string) string {
	raw := strings.Join([]string{
		strings.TrimSpace(authorID),
		strings.TrimSpace(helpType),
		strings.TrimSpace(action),
		strings.TrimSpace(dimension),
		strings.TrimSpace(tagRef),
		strings.TrimSpace(source),
	}, "|")
	sum := sha1.Sum([]byte(raw))
	return hex.EncodeToString(sum[:])[:20]
}

// NormalizeImpactTags trims, de-duplicates and drops empty intersection tag refs.
func NormalizeImpactTags(tags []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(tags))
	for _, tag := range tags {
		trimmed := strings.TrimSpace(tag)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
	}
	return out
}
