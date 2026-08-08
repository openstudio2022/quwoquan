package readiness

import (
	"encoding/json"
	"fmt"
	"strings"

	"quwoquan_service/internal/metadata/graph"
)

type pageTarget struct {
	participants  map[string]struct{}
	physicalOwner string
}

type pageTargetCatalog map[string]pageTarget

// currentPageTargets reads page identity and participation from the canonical
// page contract already embedded in the current ContractGraph documents. It
// does not read the worktree, so evaluation cannot silently mix a graph with a
// newer page contract.
func currentPageTargets(current *graph.ContractGraph) (pageTargetCatalog, error) {
	identities, err := currentObjectPathIdentities(current)
	if err != nil {
		return nil, err
	}
	return currentPageTargetsWithIdentities(current, identities)
}

func currentPageTargetsWithIdentities(
	current *graph.ContractGraph,
	identities map[string]objectPathIdentity,
) (pageTargetCatalog, error) {
	result := pageTargetCatalog{}
	found := false
	for _, document := range current.Documents {
		if !strings.HasSuffix(document.Path, "_shared/page_object_contract.yaml") {
			continue
		}
		if found {
			return nil, fmt.Errorf("current ContractGraph contains duplicate page contracts")
		}
		found = true
		var value struct {
			Pages []struct {
				PageID     string   `json:"page_id"`
				ObjectIDs  []string `json:"object_ids"`
				SourcePath string   `json:"source_path"`
			} `json:"pages"`
		}
		if err := json.Unmarshal(document.Content, &value); err != nil {
			return nil, fmt.Errorf("decode current page contract: %w", err)
		}
		for _, page := range value.Pages {
			pageID := strings.TrimSpace(page.PageID)
			if pageID == "" {
				return nil, fmt.Errorf("current page contract contains an empty page id")
			}
			if _, duplicate := result[pageID]; duplicate {
				return nil, fmt.Errorf("current page contract contains duplicate page %q", pageID)
			}
			objects := map[string]struct{}{}
			for _, objectID := range page.ObjectIDs {
				objectID = strings.TrimSpace(objectID)
				if objectID != "" {
					objects[objectID] = struct{}{}
				}
			}
			result[pageID] = pageTarget{
				participants:  objects,
				physicalOwner: physicalPageOwner(page.SourcePath, identities),
			}
		}
	}
	return result, nil
}

// physicalPageOwner reads the canonical App object tree shape
// `lib/service/<service>_service/<context>/<object>/presentation/<file>.dart`,
// with the exact service segment derived into this ContractGraph's evidence by
// `load/evidence.go`. A merely non-empty service segment cannot claim an object.
// Shell, design-system and runtime pages have no object owner and return "".
func physicalPageOwner(
	sourcePath string,
	identities map[string]objectPathIdentity,
) string {
	segments := strings.Split(strings.TrimSpace(sourcePath), "/")
	if len(segments) < 7 || segments[0] != "lib" || segments[1] != "service" ||
		segments[5] != "presentation" {
		return ""
	}
	if segments[2] == "" || segments[3] == "" || segments[4] == "" {
		return ""
	}
	objectID := segments[3] + "." + segments[4]
	identity, exists := identities[objectID]
	if !exists || identity.appServiceRoot == "" ||
		segments[2] != identity.appServiceRoot || segments[3] != identity.context ||
		segments[4] != identity.object {
		return ""
	}
	return objectID
}
