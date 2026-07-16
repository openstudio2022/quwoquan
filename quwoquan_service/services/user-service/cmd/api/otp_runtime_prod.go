//go:build !nonprod

package main

import "fmt"

func nonProductionFixedOTPGenerator() (func() (string, error), error) {
	return nil, fmt.Errorf("fixed_test OTP provider is not compiled into this binary")
}
