package readiness

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// ContractGraphSourceHash derives the identity of the exact metadata source
// set carried by the current ContractGraph. The compiler already binds every
// source path to its bytes; hashing the sorted path/digest pairs avoids trusting
// a caller-supplied hash that may describe a different graph.
func ContractGraphSourceHash(current *graph.ContractGraph) (string, error) {
	if current == nil || len(current.Sources) == 0 {
		return "", fmt.Errorf("current ContractGraph has no source identities")
	}
	sources := append([]ast.SourceDigest(nil), current.Sources...)
	sort.Slice(sources, func(i, j int) bool {
		if sources[i].Path != sources[j].Path {
			return sources[i].Path < sources[j].Path
		}
		return sources[i].SHA256 < sources[j].SHA256
	})
	hash := sha256.New()
	previousPath := ""
	for _, source := range sources {
		path := strings.TrimSpace(source.Path)
		if path == "" || !isSHA256(source.SHA256) {
			return "", fmt.Errorf("ContractGraph contains an invalid source identity")
		}
		if path == previousPath {
			return "", fmt.Errorf("ContractGraph contains duplicate source path %q", path)
		}
		previousPath = path
		_, _ = hash.Write([]byte(path))
		_, _ = hash.Write([]byte{0})
		_, _ = hash.Write([]byte(source.SHA256))
		_, _ = hash.Write([]byte{'\n'})
	}
	return hex.EncodeToString(hash.Sum(nil)), nil
}
