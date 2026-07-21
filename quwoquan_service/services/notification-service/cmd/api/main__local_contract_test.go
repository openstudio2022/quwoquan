package main

import "testing"

func TestRequiredNonNegativeIntEnv(t *testing.T) {
	const key = "NOTIFICATION_REDIS_GENERAL_DB"

	testCases := []struct {
		name    string
		value   string
		want    int
		wantErr bool
	}{
		{name: "accepts zero", value: "0", want: 0},
		{name: "accepts positive partition", value: "4", want: 4},
		{name: "rejects missing", wantErr: true},
		{name: "rejects negative", value: "-1", wantErr: true},
		{name: "rejects non numeric", value: "general", wantErr: true},
	}

	for _, testCase := range testCases {
		t.Run(testCase.name, func(t *testing.T) {
			t.Setenv(key, testCase.value)

			got, err := requiredNonNegativeIntEnv(key)

			if testCase.wantErr {
				if err == nil {
					t.Fatal("expected environment validation error")
				}
				return
			}
			if err != nil {
				t.Fatalf("requiredNonNegativeIntEnv() error = %v", err)
			}
			if got != testCase.want {
				t.Fatalf("requiredNonNegativeIntEnv() = %d, want %d", got, testCase.want)
			}
		})
	}
}
