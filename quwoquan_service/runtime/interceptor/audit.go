package interceptor

import (
	"context"
	"log/slog"
	"time"
)

// AuditInterceptor logs create/update/delete operations for audit trail.
type AuditInterceptor struct {
	logger *slog.Logger
}

func NewAuditInterceptor(logger *slog.Logger) *AuditInterceptor {
	return &AuditInterceptor{logger: logger}
}

func (i *AuditInterceptor) Name() string { return "audit" }

func (i *AuditInterceptor) Intercept(ctx context.Context, ic *Context, next Handler) error {
	if ic.Operation == OpRead {
		return next(ctx, ic)
	}

	start := time.Now()
	err := next(ctx, ic)
	duration := time.Since(start)

	attrs := []slog.Attr{
		slog.String("entity", ic.EntityName),
		slog.String("operation", string(ic.Operation)),
		slog.String("entityId", ic.EntityID),
		slog.Duration("duration", duration),
	}

	if err != nil {
		attrs = append(attrs, slog.String("error", err.Error()))
		i.logger.LogAttrs(ctx, slog.LevelError, "repository.audit", attrs...)
	} else {
		i.logger.LogAttrs(ctx, slog.LevelInfo, "repository.audit", attrs...)
	}

	return err
}
