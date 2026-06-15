package application

import (
	"fmt"
	"strings"
	"time"
)

// SandboxAllowlist 描述 gamma 环境"受控放通"白名单：只有命中白名单的测试手机号/运营商 token/
// 社交测试账号才会跳过真实下发并回填可见验证码或接受沙箱身份；真实用户依旧走严格校验。
//
// 与 SmsOtpPassThroughConfig（全局放通，仅 alpha/beta 临时技术债）的区别：
//   - 全局放通：所有号码都放通，只允许非生产；
//   - 受控放通：只对白名单条目放通，gamma 对接真实上游但保留可测性，prod 必须为空。
type SandboxAllowlist struct {
	// Enabled 仅在显式开启且非生产时生效。
	Enabled bool
	// Phones 命中规则：完整号码或号段前缀（例如 "+86188" 命中 "+8618800000000"）。
	Phones []string
	// Tokens 命中规则：运营商一键 carrierToken 或社交授权 code 的完整/前缀匹配。
	Tokens []string
	// DebtID / Owner / ExpiresAt 用于审计与到期治理，开启时必填。
	DebtID    string
	Owner     string
	ExpiresAt time.Time
}

func (a SandboxAllowlist) active(now time.Time) bool {
	if !a.Enabled {
		return false
	}
	if a.ExpiresAt.IsZero() || now.After(a.ExpiresAt) {
		return false
	}
	return true
}

// AllowsPhone 判断手机号是否命中受控放通白名单。
func (a SandboxAllowlist) AllowsPhone(phone string, now time.Time) bool {
	if !a.active(now) {
		return false
	}
	normalized := strings.TrimSpace(phone)
	if normalized == "" {
		return false
	}
	return matchAny(a.Phones, normalized)
}

// AllowsToken 判断运营商 token / 社交授权码是否命中受控放通白名单。
func (a SandboxAllowlist) AllowsToken(token string, now time.Time) bool {
	if !a.active(now) {
		return false
	}
	normalized := strings.TrimSpace(token)
	if normalized == "" {
		return false
	}
	return matchAny(a.Tokens, normalized)
}

// Validate 强制：生产禁止任何受控放通白名单；开启时必须登记 debt/owner/expires。
func (a SandboxAllowlist) Validate(isProduction bool) error {
	if isProduction {
		if a.Enabled || len(a.Phones) > 0 || len(a.Tokens) > 0 {
			return fmt.Errorf("production must not configure sandbox allowlist")
		}
		return nil
	}
	if !a.Enabled {
		return nil
	}
	if len(a.Phones) == 0 && len(a.Tokens) == 0 {
		return fmt.Errorf("sandbox allowlist enabled but no phones/tokens configured")
	}
	if strings.TrimSpace(a.DebtID) == "" || strings.TrimSpace(a.Owner) == "" || a.ExpiresAt.IsZero() {
		return fmt.Errorf("sandbox allowlist requires debt_id, owner and expires_at")
	}
	return nil
}

func matchAny(patterns []string, value string) bool {
	for _, raw := range patterns {
		pattern := strings.TrimSpace(raw)
		if pattern == "" {
			continue
		}
		if value == pattern || strings.HasPrefix(value, pattern) {
			return true
		}
	}
	return false
}
