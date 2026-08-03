// Package domainreader contains typed cross-service readers used only after a
// selected Skill declares the matching resolverRef. It does not mirror domain
// objects into assistant-service storage.
package domainreader

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

const (
	tripTimelineOperation = "travel.trip_timeline_view.GetTripTimeline"
	tripMapOperation      = "travel.trip_map_view.GetTripMap"
	tripGuideOperation    = "travel.trip_guide_assignment.ListTripGuideAssignments"
	travelResponseLimit   = 2 << 20
)

type TravelContext struct {
	TripID                string
	CurrentRevisionID     string
	CurrentRevisionNumber int64
	SourceDigest          string
	ProjectedAt           time.Time
	Timeline              map[string]any
	Map                   map[string]any
	GuideAssignments      map[string]any
}

type TravelContextReader interface {
	ReadTripContext(context.Context, string, string) (TravelContext, error)
}

type TravelClient struct {
	baseURL       *url.URL
	http          *http.Client
	authorization rtauth.DelegatedPersonaAuthorizationProvider
	timelinePath  string
	mapPath       string
	guidePath     string
}

func NewTravelClient(
	baseURL string,
	httpClient *http.Client,
	authorization rtauth.DelegatedPersonaAuthorizationProvider,
) (*TravelClient, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(baseURL), "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") {
		return nil, fmt.Errorf("travel-service base URL must be absolute http or https")
	}
	if httpClient == nil {
		return nil, fmt.Errorf("travel-service observed HTTP client is required")
	}
	if authorization == nil {
		return nil, fmt.Errorf("travel-service delegated authorization is required")
	}
	timelinePath, err := operationPath(tripTimelineOperation)
	if err != nil {
		return nil, err
	}
	mapPath, err := operationPath(tripMapOperation)
	if err != nil {
		return nil, err
	}
	guidePath, err := operationPath(tripGuideOperation)
	if err != nil {
		return nil, err
	}
	return &TravelClient{
		baseURL: parsed, http: httpClient, authorization: authorization,
		timelinePath: timelinePath, mapPath: mapPath, guidePath: guidePath,
	}, nil
}

func (client *TravelClient) ReadTripContext(
	ctx context.Context,
	personaID string,
	tripID string,
) (TravelContext, error) {
	personaID = strings.TrimSpace(personaID)
	tripID = strings.TrimSpace(tripID)
	if client == nil || client.http == nil || client.authorization == nil || personaID == "" || tripID == "" {
		return TravelContext{}, fmt.Errorf("travel context request is invalid")
	}
	authorization, err := client.authorization.AuthorizationHeaderForPersona(ctx, personaID)
	if err != nil {
		return TravelContext{}, fmt.Errorf("authorize travel context request: %w", err)
	}
	timeline, err := client.read(ctx, client.timelinePath, tripID, authorization)
	if err != nil {
		return TravelContext{}, err
	}
	tripMap, err := client.read(ctx, client.mapPath, tripID, authorization)
	if err != nil {
		return TravelContext{}, err
	}
	guideAssignments, err := client.read(ctx, client.guidePath, tripID, authorization)
	if err != nil {
		return TravelContext{}, err
	}
	result, err := validateTravelContext(tripID, timeline, tripMap, guideAssignments)
	if err != nil {
		return TravelContext{}, err
	}
	result.Timeline = timeline
	result.Map = tripMap
	result.GuideAssignments = guideAssignments
	return result, nil
}

func (client *TravelClient) read(
	ctx context.Context,
	pathTemplate string,
	tripID string,
	authorization string,
) (map[string]any, error) {
	target := *client.baseURL
	escapedTripID := url.PathEscape(tripID)
	path := strings.ReplaceAll(pathTemplate, "{tripId}", escapedTripID)
	if strings.Contains(path, "{") || !strings.HasPrefix(path, "/") {
		return nil, fmt.Errorf("travel operation path is invalid")
	}
	target.Path = strings.TrimRight(target.Path, "/") + path
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("build travel context request: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	request.Header.Set("Accept", "application/json")
	response, err := client.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("call travel-service context reader: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 8<<10))
		return nil, fmt.Errorf("travel-service context status=%d", response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, travelResponseLimit))
	var value map[string]any
	if err := decoder.Decode(&value); err != nil {
		return nil, fmt.Errorf("decode travel-service context: %w", err)
	}
	return value, nil
}

func validateTravelContext(
	requestedTripID string,
	timeline map[string]any,
	tripMap map[string]any,
	guideAssignments map[string]any,
) (TravelContext, error) {
	timelineTripID := mapString(timeline, "tripId")
	mapTripID := mapString(tripMap, "tripId")
	guideTripID := mapString(guideAssignments, "tripId")
	revisionID := mapString(timeline, "currentRevisionId")
	mapRevisionID := mapString(tripMap, "currentRevisionId")
	revisionNumber, revisionOK := mapInt64(timeline, "currentRevisionNumber")
	mapRevisionNumber, mapRevisionOK := mapInt64(tripMap, "currentRevisionNumber")
	digest := mapString(timeline, "sourceDigest")
	mapDigest := mapString(tripMap, "sourceDigest")
	projectedAt, err := time.Parse(time.RFC3339Nano, mapString(timeline, "projectedAt"))
	if timelineTripID != requestedTripID || mapTripID != requestedTripID || guideTripID != requestedTripID ||
		revisionID == "" || revisionID != mapRevisionID || !revisionOK || !mapRevisionOK ||
		revisionNumber <= 0 || revisionNumber != mapRevisionNumber || digest == "" || digest != mapDigest || err != nil {
		return TravelContext{}, fmt.Errorf("travel context identity or source digest mismatch")
	}
	return TravelContext{
		TripID: requestedTripID, CurrentRevisionID: revisionID,
		CurrentRevisionNumber: revisionNumber, SourceDigest: digest, ProjectedAt: projectedAt.UTC(),
	}, nil
}

func operationPath(operationID string) (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("travel") {
		if descriptor.CanonicalOperationID == operationID {
			if descriptor.Method != http.MethodGet {
				return "", fmt.Errorf("travel context operation %s must use GET", operationID)
			}
			return descriptor.PathTemplate, nil
		}
	}
	return "", fmt.Errorf("missing generated travel operation descriptor %s", operationID)
}

func mapString(value map[string]any, key string) string {
	raw, _ := value[key].(string)
	return strings.TrimSpace(raw)
}

func mapInt64(value map[string]any, key string) (int64, bool) {
	switch raw := value[key].(type) {
	case float64:
		converted := int64(raw)
		return converted, raw == float64(converted)
	case int64:
		return raw, true
	case int:
		return int64(raw), true
	default:
		return 0, false
	}
}

var _ TravelContextReader = (*TravelClient)(nil)
