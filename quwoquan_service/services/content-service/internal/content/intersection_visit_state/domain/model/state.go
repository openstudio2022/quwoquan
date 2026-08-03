package model

import (
	"fmt"
	"slices"
	"strings"
)

var Dimensions = []string{"identity", "location", "content", "interest", "relationship"}

func ValidateDimension(dimension string) error {
	dimension = strings.TrimSpace(dimension)
	if dimension != "" && !slices.Contains(Dimensions, dimension) {
		return fmt.Errorf("unsupported intersection dimension")
	}
	return nil
}

// State is the durable per-persona monotonic watermark aggregate.
type State struct {
	PersonaID  string
	Watermarks map[string]int64
}

func (state State) Validate() error {
	if strings.TrimSpace(state.PersonaID) == "" {
		return fmt.Errorf("IntersectionVisitState requires persona identity")
	}
	for dimension, watermark := range state.Watermarks {
		if ValidateDimension(dimension) != nil || strings.TrimSpace(dimension) == "" || watermark <= 0 {
			return fmt.Errorf("IntersectionVisitState contains invalid watermark")
		}
	}
	return nil
}
