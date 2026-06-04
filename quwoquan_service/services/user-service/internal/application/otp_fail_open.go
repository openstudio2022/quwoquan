package application

import (
	"fmt"
	"strings"
	"time"
)

const (
	SmsOtpPassThroughDisabled = "disabled"
	SmsOtpPassThroughEnabled  = "enabled"
)

type SmsOtpPassThroughConfig struct {
	Mode      string
	DebtID    string
	Owner     string
	ExpiresAt time.Time
}

func (c SmsOtpPassThroughConfig) Allows(now time.Time) bool {
	return strings.TrimSpace(c.Mode) == SmsOtpPassThroughEnabled && !c.ExpiresAt.IsZero() && !now.After(c.ExpiresAt)
}

func (c SmsOtpPassThroughConfig) Validate(isProduction bool) error {
	mode := strings.TrimSpace(c.Mode)
	if mode == "" {
		mode = SmsOtpPassThroughDisabled
	}
	if isProduction && mode != SmsOtpPassThroughDisabled {
		return fmt.Errorf("production must disable sms otp pass-through")
	}
	if mode == SmsOtpPassThroughDisabled {
		return nil
	}
	if mode != SmsOtpPassThroughEnabled {
		return fmt.Errorf("unsupported sms otp pass-through mode %q", mode)
	}
	if strings.TrimSpace(c.DebtID) == "" || strings.TrimSpace(c.Owner) == "" || c.ExpiresAt.IsZero() {
		return fmt.Errorf("sms otp pass-through requires debt_id, owner and expires_at")
	}
	return nil
}
