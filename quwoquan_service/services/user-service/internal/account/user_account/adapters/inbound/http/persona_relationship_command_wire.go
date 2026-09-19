package http

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type relationshipMutationWire struct {
	Source          string `json:"source,omitempty"`
	MutationBasis   string `json:"mutationBasis"`
	ExpectedVersion *int64 `json:"expectedVersion"`
}

type relationshipFinalizeWire struct {
	MutationBasis   string `json:"mutationBasis"`
	ExpectedVersion *int64 `json:"expectedVersion"`
}

func decodeRelationshipMutation(r *http.Request) (relationshipMutationWire, error) {
	var wire relationshipMutationWire
	if r == nil || r.Body == nil {
		return wire, errors.New("relationship command body is required")
	}
	decoder := json.NewDecoder(io.LimitReader(r.Body, 8*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&wire); err != nil {
		return wire, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return wire, errors.New("relationship command body contains trailing JSON")
	}
	wire.MutationBasis = strings.TrimSpace(wire.MutationBasis)
	if wire.MutationBasis == "" || wire.ExpectedVersion == nil || *wire.ExpectedVersion < 0 {
		return wire, errors.New("mutationBasis and expectedVersion are required")
	}
	return wire, nil
}

func decodeRelationshipFinalize(r *http.Request) (relationshipFinalizeWire, error) {
	var wire relationshipFinalizeWire
	if r == nil || r.Body == nil {
		return wire, errors.New("relationship finalize body is required")
	}
	decoder := json.NewDecoder(io.LimitReader(r.Body, 8*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&wire); err != nil {
		return wire, err
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return wire, errors.New("relationship finalize body contains trailing JSON")
	}
	wire.MutationBasis = strings.TrimSpace(wire.MutationBasis)
	if wire.MutationBasis == "" || wire.ExpectedVersion == nil || *wire.ExpectedVersion < 0 {
		return wire, errors.New("mutationBasis and expectedVersion are required")
	}
	return wire, nil
}

func parseRelationshipOperation(raw string) (relmodel.CommandKind, bool) {
	switch relmodel.CommandKind(strings.TrimSpace(raw)) {
	case relmodel.CommandFollow, relmodel.CommandUnfollow, relmodel.CommandBlock, relmodel.CommandUnblock:
		return relmodel.CommandKind(strings.TrimSpace(raw)), true
	default:
		return "", false
	}
}
