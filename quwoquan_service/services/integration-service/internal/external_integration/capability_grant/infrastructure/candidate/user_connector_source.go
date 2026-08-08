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
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
	definitionports "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/ports"
)

// ConnectorReaderSource adapts Integration-owned ConnectorConnection state to
// redacted capability candidates. credentialRef never crosses this boundary.
type ConnectorReaderSource struct {
	reader      connectionports.Reader
	definitions definitionports.Reader
	now         func() time.Time
}

func NewConnectorReaderSource(
	reader connectionports.Reader,
	definitions definitionports.Reader,
	now func() time.Time,
) *ConnectorReaderSource {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &ConnectorReaderSource{
		reader:      reader,
		definitions: definitions,
		now:         now,
	}
}

func (source *ConnectorReaderSource) UserConnectorCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
) ([]grantmodel.UserConnectorConnection, error) {
	accountID := strings.TrimSpace(requirement.AccountID)
	capabilityKey := strings.TrimSpace(requirement.CapabilityKey)
	surfaceKind := strings.TrimSpace(requirement.SurfaceKind)
	if source == nil || source.reader == nil || source.definitions == nil ||
		source.now == nil || ctx == nil || accountID == "" ||
		capabilityKey == "" || surfaceKind == "" ||
		len(requirement.ConnectionRefs) == 0 {
		return nil, grantapp.ErrCandidateSourceUnavailable
	}
	result := make(
		[]grantmodel.UserConnectorConnection,
		0,
		len(requirement.ConnectionRefs),
	)
	capabilityDenied := false
	surfaceDenied := false
	for _, connectionRef := range requirement.ConnectionRefs {
		connection, err := source.reader.Get(ctx, accountID, connectionRef)
		if errors.Is(err, connectionmodel.ErrNotFound) {
			continue
		}
		if err != nil {
			return nil, err
		}
		candidate, parseErr := grantapp.ParseUserConnectorConnection(
			accountID, capabilityKey, connection, source.now().UTC(),
		)
		if errors.Is(parseErr, grantapp.ErrUserConnectorCandidateInvalid) {
			continue
		}
		if parseErr != nil {
			return nil, parseErr
		}
		definition, definitionErr := source.definitions.Get(
			ctx,
			connection.ConnectorID,
		)
		if errors.Is(definitionErr, definitionmodel.ErrNotFound) {
			continue
		}
		if definitionErr != nil {
			return nil, definitionErr
		}
		if definition.Status != definitionmodel.StatusActive ||
			!definition.Grants(capabilityKey) ||
			!containsCapability(connection, capabilityKey) {
			capabilityDenied = true
			continue
		}
		if !definition.SupportsSurface(surfaceKind) {
			surfaceDenied = true
			continue
		}
		candidate.ContractDigest = definition.ReleaseDigest
		result = append(result, candidate)
	}
	if len(result) == 0 {
		if surfaceDenied {
			return nil, grantmodel.ErrConnectorSurfaceDenied
		}
		if capabilityDenied {
			return nil, grantmodel.ErrConnectorCapability
		}
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
