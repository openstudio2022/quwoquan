//go:build nonprod

package main

const fixedTestOTPCode = "123456"

func nonProductionFixedOTPGenerator() (func() (string, error), error) {
	return func() (string, error) { return fixedTestOTPCode, nil }, nil
}
