package application

import (
	"errors"
	"strings"
	"time"

	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

var ErrUserConnectorCandidateInvalid = errors.New(
	"user connector capability candidate is invalid",
)

// ParseUserConnectorConnection converts Integration-owned Connection state into
// the redacted candidate consumed by the four-kind resolver. It does not expose
// credentialRef or accept an account identity from an untrusted request body.
func ParseUserConnectorConnection(
	trustedAccountID string,
	capabilityKey string,
	connection connectionmodel.Connection,
	now time.Time,
) (grantmodel.UserConnectorConnection, error) {
	trustedAccountID = strings.TrimSpace(trustedAccountID)
	capabilityKey = strings.TrimSpace(capabilityKey)
	now = now.UTC()
	if trustedAccountID == "" || capabilityKey == "" || now.IsZero() ||
		strings.TrimSpace(connection.AccountID) != trustedAccountID ||
		strings.TrimSpace(connection.ConnectionID) == "" ||
		strings.TrimSpace(connection.ConnectorID) == "" {
		return grantmodel.UserConnectorConnection{}, ErrUserConnectorCandidateInvalid
	}
	state := grantmodel.ConnectorGrantState("")
	switch {
	case connection.Status == connectionmodel.StatusRevoked || connection.RevokedAt != nil:
		state = grantmodel.ConnectorGrantRevoked
	case connection.Status == connectionmodel.StatusExpired ||
		(connection.ExpiresAt != nil && !connection.ExpiresAt.After(now)):
		state = grantmodel.ConnectorGrantExpired
	case connection.Status == connectionmodel.StatusActive:
		state = grantmodel.ConnectorGrantActive
	default:
		return grantmodel.UserConnectorConnection{}, ErrUserConnectorCandidateInvalid
	}
	return grantmodel.UserConnectorConnection{
		CapabilityKey:       capabilityKey,
		AccountID:           trustedAccountID,
		ConnectionID:        strings.TrimSpace(connection.ConnectionID),
		ConnectorID:         strings.TrimSpace(connection.ConnectorID),
		GrantedCapabilities: append([]string(nil), connection.GrantedCapabilities...),
		GrantState:          state,
		ProviderAccountSubjectDigest: strings.TrimSpace(
			connection.ProviderAccountSubjectDigest,
		),
		FreshnessAt: connection.FreshnessAt.UTC(),
		ExpiresAt:   connection.ExpiresAt,
		Revision:    connection.Revision,
	}, nil
}
