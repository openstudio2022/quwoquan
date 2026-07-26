package application

import (
	"context"
	"slices"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

var dimensions = []string{"identity", "location", "content", "interest", "relationship"}

type Marker interface {
	MarkVisited(context.Context, string, string) error
}

type Commands struct{ marker Marker }

func NewCommands(marker Marker) *Commands {
	if marker == nil {
		panic("intersection visit marker is required")
	}
	return &Commands{marker: marker}
}

func (s *Commands) MarkVisited(ctx context.Context, personaID, dimension string) error {
	personaID, dimension = strings.TrimSpace(personaID), strings.TrimSpace(dimension)
	if personaID == "" {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "需要登录", "missing persona")
	}
	if dimension != "" && !slices.Contains(dimensions, dimension) {
		return rterr.NewInvalidArgument(rterr.ModuleContent, "交集维度无效", "unsupported intersection dimension")
	}
	return s.marker.MarkVisited(ctx, personaID, dimension)
}
