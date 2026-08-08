package readiness

import (
	"fmt"
	"strings"

	"quwoquan_service/internal/metadata/graph"
)

// objectPathIdentity is the evaluator-side projection of one canonical object
// location. Domain/context/object come from ContractGraph objects; serviceRoot
// comes from the corresponding loader-derived structure evidence packet. This
// keeps dynamic result validation bound to the exact graph bytes instead of a
// hand-maintained context -> service registry or a newer worktree.
type objectPathIdentity struct {
	domain         string
	context        string
	object         string
	serviceRoot    []string
	appServiceRoot string
}

// currentObjectPathIdentities derives the current roster and service-root
// ownership only from ContractGraph. Objects without implementation evidence
// remain in the roster with an empty service root; they cannot author a
// runnable Service/App case until the loader can derive a real object root.
func currentObjectPathIdentities(
	current *graph.ContractGraph,
) (map[string]objectPathIdentity, error) {
	result := make(map[string]objectPathIdentity, len(current.Objects))
	for _, object := range current.Objects {
		segments := strings.Split(strings.TrimSpace(object.SourcePath), "/")
		if len(segments) != 4 || segments[3] != "object.yaml" ||
			segments[0] == "" || segments[1] == "" || segments[2] == "" ||
			object.Domain != segments[0] || object.ID != segments[0]+"."+segments[2] {
			return nil, fmt.Errorf(
				"object %q has non-canonical ContractGraph source path %q",
				object.ID, object.SourcePath,
			)
		}
		if _, duplicate := result[object.ID]; duplicate {
			return nil, fmt.Errorf("ContractGraph contains duplicate object %q", object.ID)
		}
		result[object.ID] = objectPathIdentity{
			domain:  segments[0],
			context: segments[1],
			object:  segments[2],
		}
	}

	seenEvidence := map[string]struct{}{}
	for _, evidence := range current.ReadinessEvidence {
		identity, exists := result[evidence.ObjectID]
		if !exists {
			return nil, fmt.Errorf(
				"readiness evidence names unknown object %q", evidence.ObjectID,
			)
		}
		if _, duplicate := seenEvidence[evidence.ObjectID]; duplicate {
			return nil, fmt.Errorf(
				"ContractGraph contains duplicate readiness evidence for %q",
				evidence.ObjectID,
			)
		}
		seenEvidence[evidence.ObjectID] = struct{}{}
		segments := strings.Split(strings.TrimSpace(evidence.SourcePath), "/")
		if len(segments) != 6 || segments[0] != "quwoquan_service" ||
			(segments[1] != "services" && segments[1] != "control-plane") ||
			segments[2] == "" || segments[3] != "internal" ||
			segments[4] != identity.context || segments[5] != identity.object {
			return nil, fmt.Errorf(
				"readiness evidence for %q has non-canonical object root %q",
				evidence.ObjectID, evidence.SourcePath,
			)
		}
		identity.serviceRoot = append([]string(nil), segments[:3]...)
		identity.appServiceRoot = strings.ReplaceAll(segments[2], "-", "_")
		result[evidence.ObjectID] = identity
	}
	return result, nil
}

func contractMatchesObjectIdentity(sourcePath string, identity objectPathIdentity) bool {
	segments := strings.Split(strings.Trim(sourcePath, "/"), "/")
	return len(segments) == 4 && segments[0] == identity.domain &&
		segments[1] == identity.context && segments[2] == identity.object &&
		segments[3] == "operations.yaml"
}
