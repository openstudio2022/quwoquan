export type RuntimeRecoveryAction =
  | "absorb"
  | "retry"
  | "fallback"
  | "surface"
  | "escalate"
  | "compensate";

export type UserDisruptionLevel =
  | "silent"
  | "passiveIndicator"
  | "snackbar"
  | "inlineCard"
  | "permissionCard";

export interface RuntimeRecoveryDecision {
  action: RuntimeRecoveryAction;
  disruptionLevel: UserDisruptionLevel;
  policyId: string;
}
