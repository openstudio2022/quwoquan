package model

import "strings"

// IsContentAddressedObjectKey identifies the immutable private-object
// namespace whose deletion must be serialized with MediaAsset references.
// Keeping the namespace rule in the media domain prevents cleanup workflows
// from depending on a particular Mongo fence adapter.
func IsContentAddressedObjectKey(key string) bool {
	key = strings.Trim(strings.TrimSpace(key), "/")
	return strings.HasPrefix(key, "media/objects/sha256/") &&
		!strings.Contains(key, "..") &&
		!strings.ContainsAny(key, "?#\\")
}
