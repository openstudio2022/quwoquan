package interceptor

import (
	"context"
	"strings"

	"quwoquan_service/runtime/registry"
)

// LogMaskingInterceptor masks PII fields based on metadata log_policy before logging.
type LogMaskingInterceptor struct{}

func NewLogMaskingInterceptor() *LogMaskingInterceptor {
	return &LogMaskingInterceptor{}
}

func (i *LogMaskingInterceptor) Name() string { return "log_masking" }

func (i *LogMaskingInterceptor) Intercept(ctx context.Context, ic *Context, next Handler) error {
	err := next(ctx, ic)

	if ic.Operation == OpRead && ic.Input != nil {
		maskFieldsByPolicy(*ic.Input, ic.FieldMeta)
	}

	return err
}

func maskFieldsByPolicy(data map[string]any, fields []registry.FieldDef) {
	for _, f := range fields {
		if f.LogPolicy == "mask" || f.LogPolicy == "drop" {
			if _, ok := data[f.Name]; ok {
				if f.LogPolicy == "drop" {
					delete(data, f.Name)
				} else {
					data[f.Name] = maskValue(data[f.Name])
				}
			}
		}
	}
}

func maskValue(v any) any {
	s, ok := v.(string)
	if !ok {
		return "***"
	}
	if len(s) <= 3 {
		return "***"
	}
	return s[:1] + strings.Repeat("*", len(s)-2) + s[len(s)-1:]
}
