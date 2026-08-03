package recommendation

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	transport "quwoquan_service/services/content-service/generated/content/post"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
)

const intersectionProjectionReadTimeout = 300 * time.Millisecond

// IntersectionReaderClient is the only Content-side port to Recommendation's
// materialized intersection projections. It never computes or persists graph
// facts and rejects identity drift and non-canonical response payloads.
type IntersectionReaderClient struct {
	baseURL     string
	httpClient  *http.Client
	credentials rtauth.ServiceAuthorizationProvider
}

func NewIntersectionReaderClient(
	baseURL string,
	credentials rtauth.ServiceAuthorizationProvider,
) (*IntersectionReaderClient, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("intersection reader: valid recommendation base URL is required")
	}
	if credentials == nil {
		return nil, fmt.Errorf("intersection reader: service credentials are required")
	}
	return &IntersectionReaderClient{
		baseURL:     strings.TrimRight(parsed.String(), "/"),
		httpClient:  &http.Client{},
		credentials: credentials,
	}, nil
}

func (client *IntersectionReaderClient) SetTransport(transport http.RoundTripper) {
	if transport == nil {
		transport = http.DefaultTransport
	}
	client.httpClient.Transport = transport
}

func (client *IntersectionReaderClient) FactReasons(
	ctx context.Context,
	subjectID,
	channel string,
) ([]intersectionapp.IntersectionReasonView, error) {
	return client.listSubject(ctx, subjectID, "fact", channel)
}

func (client *IntersectionReaderClient) AffinityReasons(
	ctx context.Context,
	subjectID,
	channel string,
) ([]intersectionapp.IntersectionReasonView, error) {
	return client.listSubject(ctx, subjectID, "affinity", channel)
}

func (client *IntersectionReaderClient) listSubject(
	ctx context.Context,
	subjectID,
	intersectionClass,
	channel string,
) ([]intersectionapp.IntersectionReasonView, error) {
	normalizedSubject := strings.TrimSpace(subjectID)
	normalizedChannel := strings.TrimSpace(channel)
	if normalizedSubject == "" || (intersectionClass != "fact" && intersectionClass != "affinity") {
		return nil, fmt.Errorf("intersection reader subject query is invalid")
	}
	path := strings.Replace(
		transport.ListRecommendationSubjectIntersectionsPath,
		"{subjectId}",
		url.PathEscape(normalizedSubject),
		1,
	)
	query := url.Values{"intersectionClass": []string{intersectionClass}}
	if normalizedChannel != "" {
		query.Set("channel", normalizedChannel)
	}
	var wire transport.RecommendationIntersectionReasonSlice
	if err := client.get(ctx, path+"?"+query.Encode(), &wire); err != nil {
		return nil, err
	}
	resolvedChannel := optionalString(wire.Channel)
	if wire.SubjectId != normalizedSubject || wire.IntersectionClass != intersectionClass ||
		(resolvedChannel != normalizedChannel && resolvedChannel != "") {
		return nil, fmt.Errorf("intersection reader subject response identity mismatch")
	}
	return mapIntersectionReasons(wire.Reasons, normalizedSubject, intersectionClass)
}

func (client *IntersectionReaderClient) ObjectReasons(
	ctx context.Context,
	subjectID,
	objectID,
	objectType string,
) ([]intersectionapp.IntersectionReasonView, error) {
	normalizedSubject := strings.TrimSpace(subjectID)
	normalizedType := strings.TrimSpace(objectType)
	normalizedObject := strings.TrimSpace(objectID)
	if normalizedSubject == "" || normalizedType == "" || normalizedObject == "" {
		return nil, fmt.Errorf("intersection reader object query is invalid")
	}
	path := strings.Replace(
		transport.ListRecommendationObjectIntersectionsPath,
		"{subjectId}",
		url.PathEscape(normalizedSubject),
		1,
	)
	path = strings.Replace(path, "{objectType}", url.PathEscape(normalizedType), 1)
	path = strings.Replace(path, "{objectId}", url.PathEscape(normalizedObject), 1)
	var wire transport.RecommendationObjectIntersectionReasonSlice
	if err := client.get(ctx, path, &wire); err != nil {
		return nil, err
	}
	if wire.SubjectId != normalizedSubject || wire.ObjectType != normalizedType ||
		wire.ObjectId != normalizedObject {
		return nil, fmt.Errorf("intersection reader object response identity mismatch")
	}
	return mapIntersectionReasons(wire.Reasons, normalizedSubject, "")
}

func (client *IntersectionReaderClient) DistinctObjectSupply(
	ctx context.Context,
	supplyKey string,
) (int, error) {
	normalizedKey := strings.TrimSpace(supplyKey)
	if normalizedKey == "" {
		return 0, fmt.Errorf("intersection supply key is required")
	}
	path := strings.Replace(
		transport.GetRecommendationIntersectionSupplyPath,
		"{supplyKey}",
		url.PathEscape(normalizedKey),
		1,
	)
	var wire transport.RecommendationIntersectionSupply
	if err := client.get(ctx, path, &wire); err != nil {
		return 0, err
	}
	if wire.SupplyKey != normalizedKey || wire.DistinctObjectCount < 0 || wire.ComputedAt.IsZero() {
		return 0, fmt.Errorf("intersection supply response is invalid")
	}
	return wire.DistinctObjectCount, nil
}

func (client *IntersectionReaderClient) get(ctx context.Context, path string, target any) error {
	if client == nil || client.httpClient == nil || client.credentials == nil {
		return fmt.Errorf("intersection reader is not configured")
	}
	requestContext, cancel := context.WithTimeout(ctx, intersectionProjectionReadTimeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		client.baseURL+path,
		nil,
	)
	if err != nil {
		return err
	}
	request.Header.Set("Accept", "application/json")
	authorization, err := client.credentials.AuthorizationHeader(requestContext)
	if err != nil {
		return fmt.Errorf("intersection service authorization: %w", err)
	}
	request.Header.Set("Authorization", authorization)
	response, err := client.httpClient.Do(request)
	if err != nil {
		return fmt.Errorf("intersection projection request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("intersection projection service status %d", response.StatusCode)
	}
	decoder := json.NewDecoder(io.LimitReader(response.Body, 4*1024*1024))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode intersection projection response: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		return fmt.Errorf("intersection projection response has trailing payload")
	}
	return nil
}

func mapIntersectionReasons(
	wires []transport.IntersectionReason,
	expectedSubject,
	expectedClass string,
) ([]intersectionapp.IntersectionReasonView, error) {
	views := make([]intersectionapp.IntersectionReasonView, 0, len(wires))
	identities := make(map[string]struct{}, len(wires))
	for _, wire := range wires {
		identity := strings.TrimSpace(wire.IntersectionId)
		if identity == "" {
			return nil, fmt.Errorf("intersection reason identity is missing")
		}
		if _, exists := identities[identity]; exists {
			return nil, fmt.Errorf("intersection reason identity is duplicated")
		}
		if wire.SubjectId != "" && wire.SubjectId != expectedSubject {
			return nil, fmt.Errorf("intersection reason subject identity mismatch")
		}
		if expectedClass != "" && wire.IntersectionClass != expectedClass {
			return nil, fmt.Errorf("intersection reason class mismatch")
		}
		if wire.IntersectionClass != "fact" && wire.IntersectionClass != "affinity" {
			return nil, fmt.Errorf("intersection reason class is invalid")
		}
		identities[identity] = struct{}{}
		views = append(views, mapIntersectionReason(wire))
	}
	return views, nil
}

func mapIntersectionReason(wire transport.IntersectionReason) intersectionapp.IntersectionReasonView {
	return intersectionapp.IntersectionReasonView{
		IntersectionID: wire.IntersectionId, IntersectionClass: wire.IntersectionClass,
		Kind: wire.Kind, Vertical: wire.Vertical, Dimension: wire.Dimension,
		DisplayName: wire.DisplayName, AvatarURL: wire.AvatarUrl,
		PrimaryText: wire.PrimaryText, PrimaryTextL10nKey: wire.PrimaryTextL10nKey,
		DisplayBinding: wire.DisplayBinding, SecondaryText: wire.SecondaryText,
		WeightTier: wire.WeightTier, ObjectKind: wire.ObjectKind, Strength: wire.Strength,
		ConfidenceLabel: wire.ConfidenceLabel, ModelReasonBucket: wire.ModelReasonBucket,
		RelationKind: wire.RelationKind, RelationObjectID: wire.RelationObjectId,
		ActionType: wire.ActionType, ActionTargetID: wire.ActionTargetId, Source: wire.Source,
		TagRefs: append([]string(nil), wire.TagRefs...), FreshAt: wire.FreshAt, ExpiresAt: wire.ExpiresAt,
		IntersectionPoints:     mapIntersectionPoints(wire.IntersectionPoints),
		PointSummarySnapshotID: wire.PointSummarySnapshotId,
		FactPointCount:         wire.FactPointCount, RecommendedPointCount: wire.RecommendedPointCount,
		TotalPointCount:       wire.TotalPointCount,
		DimensionPointSummary: mapIntersectionTallies(wire.DimensionPointSummary),
		PointClassLabel:       wire.PointClassLabel, ConnectionSummary: wire.ConnectionSummary,
		LastRecommendedAt: wire.LastRecommendedAt, SeenAt: wire.SeenAt, RankState: wire.RankState,
		PrimarySpans:              mapIntersectionTextSpans(wire.PrimarySpans),
		SampleVisuals:             mapIntersectionVisuals(wire.SampleVisuals),
		RepresentativeActor:       mapIntersectionRepresentativeActor(wire.RepresentativeActor),
		ActorEvidenceTotalCount:   wire.ActorEvidenceTotalCount,
		ActorEvidenceCompleteness: wire.ActorEvidenceCompleteness,
		ActorEvidence:             mapIntersectionActorEvidence(wire.ActorEvidence),
		ActionHints:               mapIntersectionActionHints(wire.ActionHints),
		LifecycleState:            wire.LifecycleState, PreviousStrength: wire.PreviousStrength,
		StrengthDelta: wire.StrengthDelta, EdgeWeight: wire.EdgeWeight,
		IconKey: wire.IconKey, Tone: wire.Tone,
		TypeVisual:   mapIntersectionVisual(wire.TypeVisual),
		ObjectVisual: mapIntersectionVisual(wire.ObjectVisual),
		TimeBucket:   wire.TimeBucket, DedupeKey: wire.DedupeKey,
		AnchorUserWeight: wire.AnchorUserWeight, MutualCount: wire.MutualCount,
		Moment: wire.Moment, SubjectID: wire.SubjectId, SubjectContext: wire.SubjectContext,
	}
}

func mapIntersectionTarget(wire *transport.IntersectionTarget) *intersectionapp.IntersectionTargetView {
	if wire == nil {
		return nil
	}
	return &intersectionapp.IntersectionTargetView{
		ObjectType: wire.ObjectType, ObjectID: wire.ObjectId,
		ObjectKind: wire.ObjectKind, RouteID: wire.RouteId,
	}
}

func mapIntersectionVisual(wire *transport.IntersectionVisual) *intersectionapp.IntersectionVisualView {
	if wire == nil {
		return nil
	}
	return &intersectionapp.IntersectionVisualView{
		AssetKind: wire.AssetKind, ImageURL: wire.ImageUrl,
		DisplayName: wire.DisplayName, Target: mapIntersectionTarget(wire.Target),
	}
}

func mapIntersectionVisuals(wires []transport.IntersectionVisual) []intersectionapp.IntersectionVisualView {
	views := make([]intersectionapp.IntersectionVisualView, 0, len(wires))
	for i := range wires {
		views = append(views, *mapIntersectionVisual(&wires[i]))
	}
	return views
}

func mapIntersectionTextSpans(wires []transport.IntersectionTextSpan) []intersectionapp.IntersectionTextSpanView {
	views := make([]intersectionapp.IntersectionTextSpanView, 0, len(wires))
	for _, wire := range wires {
		views = append(views, intersectionapp.IntersectionTextSpanView{
			Text: wire.Text, Role: wire.Role, Target: mapIntersectionTarget(wire.Target),
			Visual: mapIntersectionVisual(wire.Visual),
		})
	}
	return views
}

func mapIntersectionPoints(wires []transport.IntersectionPoint) []intersectionapp.IntersectionPointView {
	views := make([]intersectionapp.IntersectionPointView, 0, len(wires))
	for _, wire := range wires {
		views = append(views, intersectionapp.IntersectionPointView{
			PointID: wire.PointId, PointClass: wire.PointClass, Dimension: wire.Dimension,
			Label: wire.Label, DisplayText: wire.DisplayText, SourceRef: wire.SourceRef,
			Visibility: wire.Visibility, Count: wire.Count, SampleText: wire.SampleText,
			SampleAvatarURLs: append([]string(nil), wire.SampleAvatarUrls...),
			SampleVisuals:    mapIntersectionVisuals(wire.SampleVisuals),
		})
	}
	return views
}

func mapIntersectionTallies(wires []transport.IntersectionDimensionTally) []intersectionapp.IntersectionDimensionTallyView {
	views := make([]intersectionapp.IntersectionDimensionTallyView, 0, len(wires))
	for _, wire := range wires {
		views = append(views, intersectionapp.IntersectionDimensionTallyView{
			Dimension: wire.Dimension, Label: wire.Label, Count: wire.Count, NewCount: wire.NewCount,
			BriefText: wire.BriefText, SubtitleText: wire.SubtitleText,
			BriefSpans:    mapIntersectionTextSpans(wire.BriefSpans),
			SampleVisuals: mapIntersectionVisuals(wire.SampleVisuals), SourceRef: wire.SourceRef,
			CountObjectKind: wire.CountObjectKind, StrengthenedCount: wire.StrengthenedCount,
			ReactivatedCount: wire.ReactivatedCount, IconKey: wire.IconKey,
		})
	}
	return views
}

func mapIntersectionRepresentativeActor(wire *transport.IntersectionRepresentativeActor) *intersectionapp.IntersectionRepresentativeActorView {
	if wire == nil {
		return nil
	}
	return &intersectionapp.IntersectionRepresentativeActorView{
		ActorID: wire.ActorId, DisplayName: wire.DisplayName, AvatarURL: wire.AvatarUrl,
		RelationLabel: wire.RelationLabel, PrivacyState: wire.PrivacyState,
		Target: mapIntersectionTarget(wire.Target), EvidenceRank: wire.EvidenceRank,
		SnapshotVersion: wire.SnapshotVersion,
	}
}

func mapIntersectionActorEvidence(wires []transport.IntersectionActorEvidence) []intersectionapp.IntersectionActorEvidenceView {
	views := make([]intersectionapp.IntersectionActorEvidenceView, 0, len(wires))
	for _, wire := range wires {
		views = append(views, intersectionapp.IntersectionActorEvidenceView{
			ActorID: wire.ActorId, DisplayName: wire.DisplayName, AvatarURL: wire.AvatarUrl,
			RelationLabel: wire.RelationLabel, RelationSourceRef: wire.RelationSourceRef,
			RelationObjectID: wire.RelationObjectId, RelationObjectName: wire.RelationObjectName,
			SourcePointID: wire.SourcePointId, SourceRef: wire.SourceRef,
			ActionSummaryText: wire.ActionSummaryText, LikeCount: wire.LikeCount,
			CommentCount: wire.CommentCount, ShareCount: wire.ShareCount,
			PrivacyState: wire.PrivacyState, Target: mapIntersectionTarget(wire.Target),
			EvidenceRank: wire.EvidenceRank, SnapshotVersion: wire.SnapshotVersion,
			SortKey: wire.SortKey,
		})
	}
	return views
}

func mapIntersectionActionHints(wires []transport.IntersectionActionHint) []intersectionapp.IntersectionActionHintView {
	views := make([]intersectionapp.IntersectionActionHintView, 0, len(wires))
	for _, wire := range wires {
		views = append(views, intersectionapp.IntersectionActionHintView{
			ActionKey: wire.ActionKey, Label: wire.Label, Target: mapIntersectionTarget(wire.Target),
			IsPrimary: wire.IsPrimary, Priority: wire.Priority, ActionTier: wire.ActionTier,
			RequiredGates: append([]string(nil), wire.RequiredGates...), Dispatch: wire.Dispatch,
		})
	}
	return views
}

var _ intersectionapp.IntersectionSource = (*IntersectionReaderClient)(nil)
var _ intersectionapp.IntersectionSupplyProbe = (*IntersectionReaderClient)(nil)
