package candidate

import (
	"context"
	"errors"
	"strings"
	"time"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	connectionports "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/ports"
)

const connectorCandidateReadLimit = 100

// ConnectorReaderSource adapts Integration-owned ConnectorConnection state to
// redacted capability candidates. credentialRef never crosses this boundary.
type ConnectorReaderSource struct {
	reader connectionports.Reader
	now    func() time.Time
}

func NewConnectorReaderSource(
	reader connectionports.Reader,
	now func() time.Time,
) *ConnectorReaderSource {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &ConnectorReaderSource{reader: reader, now: now}
}

func (source *ConnectorReaderSource) UserConnectorCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
) ([]grantmodel.UserConnectorConnection, error) {
	accountID := strings.TrimSpace(requirement.AccountID)
	capabilityKey := strings.TrimSpace(requirement.CapabilityKey)
	if source == nil || source.reader == nil || source.now == nil ||
		ctx == nil || accountID == "" || capabilityKey == "" {
		return nil, grantapp.ErrCandidateSourceUnavailable
	}
	connections, err := source.reader.List(ctx, accountID, connectorCandidateReadLimit)
	if err != nil {
		return nil, err
	}
	result := make([]grantmodel.UserConnectorConnection, 0, len(connections))
	for _, connection := range connections {
		candidate, parseErr := grantapp.ParseUserConnectorConnection(
			accountID, capabilityKey, connection, source.now().UTC(),
		)
		if errors.Is(parseErr, grantapp.ErrUserConnectorCandidateInvalid) {
			continue
		}
		if parseErr != nil {
			return nil, parseErr
		}
		if candidate.GrantState == grantmodel.ConnectorGrantActive &&
			!containsCapability(connection, capabilityKey) {
			continue
		}
		result = append(result, candidate)
	}
	return result, nil
}

func containsCapability(connection connectionmodel.Connection, capabilityKey string) bool {
	for _, capability := range connection.GrantedCapabilities {
		if strings.TrimSpace(capability) == capabilityKey {
			return true
		}
	}
	return false
}
