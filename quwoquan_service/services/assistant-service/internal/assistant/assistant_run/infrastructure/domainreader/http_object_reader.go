package domainreader

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
	"unicode/utf8"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

type objectReaderSpec struct {
	domain               string
	operationRef         string
	objectTypeRef        string
	pathParameter        string
	responseObjectField  string
	identityField        string
	projectionFields     []string
	requiredFields       []string
	requiredStringValues map[string][]string
	timestampFields      []string
	summaryFields        []string
	maxResponseBytes     int64
}

type httpObjectReader struct {
	baseURL    string
	http       *http.Client
	now        func() time.Time
	spec       objectReaderSpec
	descriptor rtauth.OperationSecurityDescriptor
}

func newHTTPObjectReader(
	baseURL string,
	httpClient *http.Client,
	now func() time.Time,
	spec objectReaderSpec,
) (*httpObjectReader, error) {
	parsed, err := url.Parse(strings.TrimRight(strings.TrimSpace(baseURL), "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" || parsed.User != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.RawQuery != "" || parsed.Fragment != "" {
		return nil, fmt.Errorf("%s base URL must be absolute http or https", spec.domain)
	}
	if httpClient == nil {
		return nil, fmt.Errorf("%s observed HTTP client is required", spec.domain)
	}
	if now == nil {
		now = time.Now
	}
	descriptor, err := publicReadDescriptor(spec)
	if err != nil {
		return nil, err
	}
	if err := validateObjectReaderSpec(spec, descriptor); err != nil {
		return nil, err
	}
	return &httpObjectReader{
		baseURL:    strings.TrimRight(parsed.String(), "/"),
		http:       httpClient,
		now:        now,
		spec:       spec,
		descriptor: descriptor,
	}, nil
}

func (reader *httpObjectReader) ReadObjectContext(
	ctx context.Context,
	target ObjectTarget,
) (ObjectContext, error) {
	if reader == nil || reader.http == nil ||
		strings.TrimSpace(target.ObjectTypeRef) != reader.spec.objectTypeRef ||
		strings.TrimSpace(target.ObjectID) == "" {
		return ObjectContext{}, fmt.Errorf("domain object context request is invalid")
	}
	objectID := strings.TrimSpace(target.ObjectID)
	path := strings.Replace(
		reader.descriptor.PathTemplate,
		"{"+reader.spec.pathParameter+"}",
		url.PathEscape(objectID),
		1,
	)
	if strings.ContainsAny(path, "{}") || !strings.HasPrefix(path, "/") {
		return ObjectContext{}, fmt.Errorf("domain object operation path is invalid")
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		reader.baseURL+path,
		nil,
	)
	if err != nil {
		return ObjectContext{}, fmt.Errorf("build domain object context request: %w", err)
	}
	request.Header.Set("Accept", "application/json")
	response, err := reader.http.Do(request)
	if err != nil {
		return ObjectContext{}, fmt.Errorf("read canonical domain object: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 8<<10))
		return ObjectContext{}, fmt.Errorf(
			"canonical domain object status=%d operation=%s",
			response.StatusCode,
			reader.spec.operationRef,
		)
	}
	raw, err := io.ReadAll(io.LimitReader(response.Body, reader.spec.maxResponseBytes+1))
	if err != nil || int64(len(raw)) > reader.spec.maxResponseBytes {
		return ObjectContext{}, fmt.Errorf("canonical domain object response exceeds bounded reader budget")
	}
	value, err := decodeObjectResponse(raw, reader.spec.responseObjectField)
	if err != nil {
		return ObjectContext{}, err
	}
	projected, err := projectObjectContext(value, objectID, reader.spec)
	if err != nil {
		return ObjectContext{}, err
	}
	canonical, err := json.Marshal(projected)
	if err != nil {
		return ObjectContext{}, fmt.Errorf("encode canonical domain object context: %w", err)
	}
	digest := sha256.Sum256(canonical)
	return ObjectContext{
		Target:       ObjectTarget{ObjectTypeRef: reader.spec.objectTypeRef, ObjectID: objectID},
		OperationRef: reader.spec.operationRef,
		CapturedAt:   reader.now().UTC(),
		SourceDigest: "sha256:" + hex.EncodeToString(digest[:]),
		TokenCost:    (len(canonical) + 3) / 4,
		Value:        projected,
		Summary:      objectSummary(reader.spec, objectID, projected),
	}, nil
}

func publicReadDescriptor(
	spec objectReaderSpec,
) (rtauth.OperationSecurityDescriptor, error) {
	for _, descriptor := range operationsecurity.ForDomain(spec.domain) {
		if descriptor.CanonicalOperationID != spec.operationRef {
			continue
		}
		if descriptor.Method != http.MethodGet || descriptor.OperationKind != "query" ||
			descriptor.CommercialStatus != "ready" || descriptor.AuthMode != "optional" ||
			descriptor.ActorRequirement != "none" || descriptor.Principal != "public" {
			return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
				"domain reader operation %s is not a ready public query",
				spec.operationRef,
			)
		}
		return descriptor, nil
	}
	return rtauth.OperationSecurityDescriptor{}, fmt.Errorf(
		"missing generated domain reader operation %s",
		spec.operationRef,
	)
}

func validateObjectReaderSpec(
	spec objectReaderSpec,
	descriptor rtauth.OperationSecurityDescriptor,
) error {
	placeholder := "{" + strings.TrimSpace(spec.pathParameter) + "}"
	if spec.domain == "" || spec.operationRef == "" || spec.objectTypeRef == "" ||
		spec.identityField == "" || spec.pathParameter == "" ||
		spec.maxResponseBytes <= 0 || strings.Count(descriptor.PathTemplate, placeholder) != 1 {
		return fmt.Errorf("invalid domain object reader specification for %s", spec.operationRef)
	}
	remainder := strings.Replace(descriptor.PathTemplate, placeholder, "", 1)
	if strings.ContainsAny(remainder, "{}") {
		return fmt.Errorf("domain object reader path has unbound parameters: %s", spec.operationRef)
	}
	projected := make(map[string]struct{}, len(spec.projectionFields))
	for _, field := range spec.projectionFields {
		field = strings.TrimSpace(field)
		if field == "" {
			return fmt.Errorf("domain object reader has a blank projection field")
		}
		if _, duplicate := projected[field]; duplicate {
			return fmt.Errorf("domain object reader has duplicate projection field %s", field)
		}
		projected[field] = struct{}{}
	}
	if _, ok := projected[spec.identityField]; !ok {
		return fmt.Errorf("domain object reader identity is not projected")
	}
	for field, allowed := range spec.requiredStringValues {
		if _, ok := projected[field]; !ok || len(allowed) == 0 {
			return fmt.Errorf("domain object reader policy field %s is invalid", field)
		}
	}
	return nil
}

func decodeObjectResponse(raw []byte, responseObjectField string) (map[string]any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var envelope map[string]any
	if err := decoder.Decode(&envelope); err != nil || envelope == nil {
		return nil, fmt.Errorf("decode canonical domain object response")
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return nil, fmt.Errorf("canonical domain object response has trailing data")
	}
	if responseObjectField == "" {
		return envelope, nil
	}
	value, ok := envelope[responseObjectField].(map[string]any)
	if !ok || value == nil {
		return nil, fmt.Errorf("canonical domain object response envelope is invalid")
	}
	return value, nil
}

func projectObjectContext(
	value map[string]any,
	objectID string,
	spec objectReaderSpec,
) (map[string]any, error) {
	identity, ok := value[spec.identityField].(string)
	if !ok || strings.TrimSpace(identity) != objectID {
		return nil, fmt.Errorf("canonical domain object identity mismatch")
	}
	for _, field := range spec.requiredFields {
		if raw, exists := value[field]; !exists || raw == nil {
			return nil, fmt.Errorf("canonical domain object required field %s is unavailable", field)
		}
	}
	for field, allowed := range spec.requiredStringValues {
		raw, ok := value[field].(string)
		if !ok || !containsString(allowed, strings.TrimSpace(raw)) {
			return nil, fmt.Errorf("canonical domain object policy rejected field %s", field)
		}
	}
	for _, field := range spec.timestampFields {
		raw, exists := value[field]
		if !exists || raw == nil {
			continue
		}
		text, ok := raw.(string)
		if !ok {
			return nil, fmt.Errorf("canonical domain object timestamp %s is invalid", field)
		}
		if _, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(text)); err != nil {
			return nil, fmt.Errorf("canonical domain object timestamp %s is invalid", field)
		}
	}
	projected := make(map[string]any, len(spec.projectionFields))
	for _, field := range spec.projectionFields {
		if raw, exists := value[field]; exists {
			projected[field] = raw
		}
	}
	return projected, nil
}

func objectSummary(spec objectReaderSpec, objectID string, value map[string]any) string {
	label := ""
	for _, field := range spec.summaryFields {
		if raw, ok := value[field].(string); ok && strings.TrimSpace(raw) != "" {
			label = strings.TrimSpace(raw)
			break
		}
	}
	if utf8.RuneCountInString(label) > 160 {
		label = string([]rune(label)[:160])
	}
	if label == "" {
		return fmt.Sprintf("%s %s", spec.objectTypeRef, objectID)
	}
	return fmt.Sprintf("%s %s: %s", spec.objectTypeRef, objectID, label)
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == wanted {
			return true
		}
	}
	return false
}

var _ ObjectContextReader = (*httpObjectReader)(nil)
