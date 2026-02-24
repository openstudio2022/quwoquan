package interceptor

import (
	"context"

	"quwoquan_service/runtime/registry"
)

// APIExposureInterceptor filters entity fields based on api_exposure metadata.
// On read: drops fields where api_exposure = "drop".
// On write: drops fields where api_exposure = "read" (not writable).
type APIExposureInterceptor struct{}

func NewAPIExposureInterceptor() *APIExposureInterceptor {
	return &APIExposureInterceptor{}
}

func (i *APIExposureInterceptor) Name() string { return "api_exposure" }

func (i *APIExposureInterceptor) Intercept(ctx context.Context, ic *Context, next Handler) error {
	if ic.Operation == OpCreate || ic.Operation == OpUpdate {
		if ic.Input != nil {
			filterWriteFields(*ic.Input, ic.FieldMeta)
		}
	}

	err := next(ctx, ic)

	if ic.Operation == OpRead && ic.Input != nil {
		filterReadFields(*ic.Input, ic.FieldMeta)
	}

	return err
}

func filterWriteFields(data map[string]any, fields []registry.FieldDef) {
	readOnly := make(map[string]bool)
	for _, f := range fields {
		if f.APIExposure == "read" || f.APIExposure == "drop" {
			readOnly[f.Name] = true
		}
	}
	for k := range data {
		if readOnly[k] {
			delete(data, k)
		}
	}
}

func filterReadFields(data map[string]any, fields []registry.FieldDef) {
	dropFields := make(map[string]bool)
	for _, f := range fields {
		if f.APIExposure == "drop" {
			dropFields[f.Name] = true
		}
	}
	for k := range data {
		if dropFields[k] {
			delete(data, k)
		}
	}
}
