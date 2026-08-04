package skill

import (
	"strings"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type Router struct {
	Catalog []Manifest
}

func NewRouter(catalog []Manifest) Router {
	return Router{Catalog: append([]Manifest{}, catalog...)}
}

func (r Router) Route(turn assistant.AssistantTurn) Manifest {
	if len(r.Catalog) == 0 {
		return Manifest{}
	}
	if turn.SkillID != "" {
		for _, manifest := range r.Catalog {
			if manifest.SkillID == turn.SkillID {
				return manifest
			}
		}
	}
	input := strings.ToLower(turn.Input.Text)
	best := Manifest{}
	bestScore := 0
	bestSpecificity := 0
	for _, manifest := range r.Catalog {
		score := 0
		specificity := 0
		for _, hint := range manifest.RoutingHints {
			if matched, weight := matchRoutingHint(input, hint); matched {
				score += weight
				specificity += len([]rune(strings.ReplaceAll(hint, " ", "")))
			}
		}
		if score > bestScore || (score == bestScore && specificity > bestSpecificity) {
			best = manifest
			bestScore = score
			bestSpecificity = specificity
		}
	}
	if bestScore > 0 {
		return best
	}
	for _, manifest := range r.Catalog {
		if manifest.RoutingFallback {
			return manifest
		}
	}
	return Manifest{}
}

// matchRoutingHint keeps routing semantics in package assets while supporting
// a small declarative conjunction: whitespace-separated terms must all occur
// in the input. A conjunction carries the number of matched terms as weight,
// so a specific intent such as "安排 行程" wins over either generic term.
func matchRoutingHint(input, hint string) (bool, int) {
	terms := strings.Fields(strings.ToLower(hint))
	if len(terms) == 0 {
		return false, 0
	}
	for _, term := range terms {
		if !strings.Contains(input, term) {
			return false, 0
		}
	}
	return true, len(terms)
}
