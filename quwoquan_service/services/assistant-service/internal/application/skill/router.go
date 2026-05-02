package skill

import (
	"strings"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type Router struct {
	Catalog []Manifest
}

func NewRouter(catalog []Manifest) Router {
	return Router{Catalog: append([]Manifest{}, catalog...)}
}

func (r Router) Route(turn assistant.AssistantTurn) Manifest {
	if len(r.Catalog) == 0 {
		return DefaultManifest()
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
			if hint != "" && strings.Contains(input, strings.ToLower(hint)) {
				score++
				specificity += len([]rune(hint))
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
		if manifest.SkillID == "fallback_general_search" {
			return manifest
		}
	}
	return r.Catalog[0]
}
