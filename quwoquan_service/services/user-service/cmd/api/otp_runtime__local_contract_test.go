//go:build nonprod

package main

import "testing"

func TestOTPCodeGeneratorDefaultsToFixedCodeOutsideProd(t *testing.T) {
	t.Setenv("USER_AUTH_OTP_MODE", "")
	for _, env := range []string{"alpha", "beta", "gamma"} {
		generator, err := otpCodeGeneratorForEnvironment(env)
		if err != nil {
			t.Fatalf("%s generator: %v", env, err)
		}
		code, err := generator()
		if err != nil || code != fixedTestOTPCode {
			t.Fatalf("%s code = %q, err=%v", env, code, err)
		}
	}
}

func TestOTPCodeGeneratorForbidsFixedModeInProd(t *testing.T) {
	t.Setenv("USER_AUTH_OTP_MODE", otpModeFixedTest)
	if _, err := otpCodeGeneratorForEnvironment("prod"); err == nil {
		t.Fatal("prod must reject fixed_test OTP mode")
	}
}
