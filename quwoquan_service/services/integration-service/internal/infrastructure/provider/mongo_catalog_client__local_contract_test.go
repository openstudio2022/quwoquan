package provider

import "testing"

func TestHaversineMeters_UsesGeographicDistance(t *testing.T) {
	t.Parallel()

	distance := haversineMeters(30.2431, 120.1505, 30.2460, 120.1518)

	if distance < 300 || distance > 400 {
		t.Fatalf("distance=%d, want 300..400", distance)
	}
}

func TestHaversineMeters_SamePointIsZero(t *testing.T) {
	t.Parallel()

	if distance := haversineMeters(30.2431, 120.1505, 30.2431, 120.1505); distance != 0 {
		t.Fatalf("distance=%d, want 0", distance)
	}
}
