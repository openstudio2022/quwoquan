package recpolicy

import (
	"context"
	"log/slog"
	"os"
	"time"
)

// SyncConfig configures the policy hot-reload loop.
type SyncConfig struct {
	// Path is the live policy YAML to reload from. Empty disables the loop
	// (the store keeps serving the seeded baseline).
	Path string
	// Interval is the reload poll period. Defaults to 30s; a short interval in
	// dev gives near-immediate "edit yaml -> takes effect" behavior.
	Interval time.Duration
	// OnReload（可选）在每次 reload 尝试后回调（N1-2 观测挂点：成功传
	// (policyDigest, nil)，失败传 ("", err)）。recpolicy 不反向依赖
	// recommendation 指标包，经装配回调解耦。
	OnReload func(digest string, err error)
}

// StartSyncLoop reloads the policy file on a ticker, applying it through the
// Store (validate-before-swap + last-good). It mirrors the product-ops
// config_sync loop shape (startup load + periodic reload + structured
// consistency logging) without a control-plane dependency: the file is the
// source and the logged effective hash is the consistency signal. A reload is
// attempted only when the file's mtime changes, so steady state is cheap.
//
// Blocks until ctx is cancelled; run it in a goroutine.
func StartSyncLoop(ctx context.Context, store *Store, logger *slog.Logger, cfg SyncConfig) {
	if store == nil || cfg.Path == "" {
		return
	}
	if cfg.Interval <= 0 {
		cfg.Interval = 30 * time.Second
	}
	if logger == nil {
		logger = slog.Default()
	}

	var lastMod time.Time
	reload := func(reason string) {
		info, statErr := os.Stat(cfg.Path)
		if statErr != nil {
			logger.Warn("recpolicy.sync.stat_failed", slog.String("path", cfg.Path), slog.String("err", statErr.Error()))
			return
		}
		if !info.ModTime().After(lastMod) {
			return
		}
		hash, err := store.ApplyFile(cfg.Path)
		if err != nil {
			// last-good retained; surface the rejection but keep serving.
			if cfg.OnReload != nil {
				cfg.OnReload("", err)
			}
			logger.Error("recpolicy.sync.rejected",
				slog.String("reason", reason),
				slog.String("path", cfg.Path),
				slog.String("effectiveHash", hash),
				slog.String("err", err.Error()))
			return
		}
		lastMod = info.ModTime()
		if cfg.OnReload != nil {
			cfg.OnReload(hash, nil)
		}
		logger.Info("recpolicy.sync.applied",
			slog.String("reason", reason),
			slog.String("path", cfg.Path),
			slog.String("policyDigest", hash))
	}

	reload("startup")
	ticker := time.NewTicker(cfg.Interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			reload("tick")
		}
	}
}
