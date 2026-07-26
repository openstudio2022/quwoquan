package taxonomyvalidation

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	behaviorapp "quwoquan_service/services/content-service/internal/content/post/application/behavior"
)

const tagValidateOperationID = "tag.tag_node_view.ValidateTagRefs"

// HTTPActiveTaxonomyLeafValidator is content-service's typed first-party
// tag-service adapter for onboarding taxonomy verification. It consumes the
// generated operation descriptor instead of duplicating a route string.
type HTTPActiveTaxonomyLeafValidator struct {
	baseURL string
	path    string
	client  *http.Client
	timeout time.Duration
}

type HTTPActiveTaxonomyLeafValidatorOption func(*HTTPActiveTaxonomyLeafValidator)

// WithHTTPClient is available to focused adapter tests and composition wiring.
func WithHTTPClient(client *http.Client) HTTPActiveTaxonomyLeafValidatorOption {
	return func(validator *HTTPActiveTaxonomyLeafValidator) {
		if client != nil {
			validator.client = client
		}
	}
}

func NewHTTPActiveTaxonomyLeafValidator(
	baseURL string,
	timeout time.Duration,
	options ...HTTPActiveTaxonomyLeafValidatorOption,
) (*HTTPActiveTaxonomyLeafValidator, error) {
	parsed, err := url.Parse(strings.TrimSpace(baseURL))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation requires a valid tag-service endpoint",
		)
	}
	if timeout <= 0 {
		return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation requires a positive request timeout",
		)
	}
	path, err := tagValidatePath()
	if err != nil {
		return nil, err
	}
	validator := &HTTPActiveTaxonomyLeafValidator{
		baseURL: strings.TrimRight(parsed.String(), "/"),
		path:    path,
		client:  &http.Client{Timeout: timeout},
		timeout: timeout,
	}
	for _, option := range options {
		if option != nil {
			option(validator)
		}
	}
	return validator, nil
}

func tagValidatePath() (string, error) {
	for _, descriptor := range operationsecurity.ForDomain("tag") {
		if descriptor.CanonicalOperationID != tagValidateOperationID {
			continue
		}
		if descriptor.Method != http.MethodPost ||
			descriptor.PathTemplate == "" ||
			strings.ContainsAny(descriptor.PathTemplate, "{}") {
			return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"tag taxonomy validation generated operation descriptor is invalid",
			)
		}
		return descriptor.PathTemplate, nil
	}
	return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
		"tag taxonomy validation generated operation descriptor is missing",
	)
}

type activeLeafValidationRequest struct {
	ExpectedTaxonomyReleaseID string   `json:"expectedTaxonomyReleaseId"`
	TagRefs                   []string `json:"tagRefs"`
}

type activeLeafValidationResponse struct {
	TaxonomyReleaseID string   `json:"taxonomyReleaseId"`
	Valid             []string `json:"valid"`
	Invalid           []string `json:"invalid"`
}

func (v *HTTPActiveTaxonomyLeafValidator) ValidateActiveTaxonomyLeaves(
	ctx context.Context,
	expectedTaxonomyReleaseID string,
	tagRefs []string,
) error {
	if v == nil || v.client == nil || strings.TrimSpace(v.baseURL) == "" || strings.TrimSpace(v.path) == "" || v.timeout <= 0 {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation adapter is not configured",
		)
	}
	expectedTaxonomyReleaseID = strings.TrimSpace(expectedTaxonomyReleaseID)
	if expectedTaxonomyReleaseID == "" {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation request omitted expected taxonomy release",
		)
	}
	canonicalTagRefs, err := canonicalTagRefs(tagRefs)
	if err != nil {
		return err
	}
	payload, err := json.Marshal(activeLeafValidationRequest{
		ExpectedTaxonomyReleaseID: expectedTaxonomyReleaseID,
		TagRefs:                   canonicalTagRefs,
	})
	if err != nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation request could not be encoded",
		)
	}

	requestContext, cancel := context.WithTimeout(ctx, v.timeout)
	defer cancel()
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodPost,
		v.baseURL+v.path,
		bytes.NewReader(payload),
	)
	if err != nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation request could not be created",
		)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Internal-Service", "content-service")

	response, err := v.client.Do(request)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(requestContext.Err(), context.DeadlineExceeded) {
			return contentgenerated.AppErrorFromUpstreamTimeout(
				"tag taxonomy validation request timed out",
			)
		}
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation request failed",
		)
	}
	defer response.Body.Close()

	switch response.StatusCode {
	case http.StatusOK:
		return validateActiveLeafResponse(
			response.Body,
			expectedTaxonomyReleaseID,
			canonicalTagRefs,
		)
	case http.StatusBadRequest:
		discardResponse(response.Body)
		return contentgenerated.AppErrorFromInvalidArgument(
			"tag taxonomy validation rejected onboarding tag refs",
		)
	case http.StatusGatewayTimeout:
		discardResponse(response.Body)
		return contentgenerated.AppErrorFromUpstreamTimeout(
			"tag taxonomy validation returned HTTP 504",
		)
	default:
		discardResponse(response.Body)
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation returned an unavailable upstream response",
		)
	}
}

func canonicalTagRefs(tagRefs []string) ([]string, error) {
	seen := make(map[string]struct{}, len(tagRefs))
	canonical := make([]string, 0, len(tagRefs))
	for _, rawTagRef := range tagRefs {
		tagRef := strings.TrimSpace(rawTagRef)
		if tagRef == "" {
			return nil, contentgenerated.AppErrorFromInvalidArgument(
				"tag taxonomy validation received an empty tagRef",
			)
		}
		if _, exists := seen[tagRef]; exists {
			continue
		}
		seen[tagRef] = struct{}{}
		canonical = append(canonical, tagRef)
	}
	if len(canonical) == 0 {
		return nil, contentgenerated.AppErrorFromInvalidArgument(
			"tag taxonomy validation requires at least one tagRef",
		)
	}
	return canonical, nil
}

func validateActiveLeafResponse(
	body io.Reader,
	expectedTaxonomyReleaseID string,
	requestedTagRefs []string,
) error {
	decoder := json.NewDecoder(io.LimitReader(body, 1024*1024))
	var response activeLeafValidationResponse
	if err := decoder.Decode(&response); err != nil {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation response could not be decoded",
		)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation response contains trailing data",
		)
	}
	if strings.TrimSpace(response.TaxonomyReleaseID) != expectedTaxonomyReleaseID {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation response snapshot does not match expected release",
		)
	}
	requested := make(map[string]struct{}, len(requestedTagRefs))
	for _, tagRef := range requestedTagRefs {
		requested[tagRef] = struct{}{}
	}
	valid, err := responseTagRefSet(response.Valid, requested)
	if err != nil {
		return err
	}
	invalid, err := responseTagRefSet(response.Invalid, requested)
	if err != nil {
		return err
	}
	for tagRef := range valid {
		if _, alsoInvalid := invalid[tagRef]; alsoInvalid {
			return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"tag taxonomy validation response classifies a tagRef more than once",
			)
		}
	}
	if len(valid)+len(invalid) != len(requested) {
		return contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"tag taxonomy validation response omits requested tagRefs",
		)
	}
	if len(invalid) > 0 {
		return contentgenerated.AppErrorFromInvalidArgument(
			"onboarding tagRefs are not active leaves in the expected taxonomy release",
		)
	}
	return nil
}

func responseTagRefSet(
	tagRefs []string,
	requested map[string]struct{},
) (map[string]struct{}, error) {
	result := make(map[string]struct{}, len(tagRefs))
	for _, rawTagRef := range tagRefs {
		tagRef := strings.TrimSpace(rawTagRef)
		if tagRef == "" {
			return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"tag taxonomy validation response contains an empty tagRef",
			)
		}
		if _, wasRequested := requested[tagRef]; !wasRequested {
			return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"tag taxonomy validation response contains an unexpected tagRef",
			)
		}
		if _, duplicate := result[tagRef]; duplicate {
			return nil, contentgenerated.AppErrorFromRequiredDependencyUnavailable(
				"tag taxonomy validation response duplicates a tagRef",
			)
		}
		result[tagRef] = struct{}{}
	}
	return result, nil
}

func discardResponse(body io.Reader) {
	_, _ = io.Copy(io.Discard, io.LimitReader(body, 1024))
}

var _ behaviorapp.ActiveTaxonomyLeafValidationPort = (*HTTPActiveTaxonomyLeafValidator)(nil)
