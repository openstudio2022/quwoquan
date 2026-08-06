// Package trust provides the production trust boundary for dynamic readiness
// evaluation. It verifies detached Ed25519 attestations and content-addressed
// evidence before exposing a snapshot or receipt to the readiness evaluator.
//
// This package never derives environment, platform, device or Provider
// identity from repository configuration. Those identities are accepted only
// from an exactly signed readiness receipt and are then matched by the parent
// evaluator against the canonical case contract.
package trust
