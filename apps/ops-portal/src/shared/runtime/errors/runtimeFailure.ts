export type RuntimeFailureOrigin =
  | "user"
  | "environment"
  | "localClient"
  | "remoteDependency"
  | "system"
  | "developer";

export type RuntimeFailureKind =
  | "validation"
  | "contract"
  | "permission"
  | "auth"
  | "network"
  | "rateLimited"
  | "unavailable"
  | "timeout"
  | "notFound"
  | "unsupported"
  | "cancelled"
  | "storage"
  | "parsing"
  | "model"
  | "internal";

export type RuntimeFailureNature =
  | "transient"
  | "permanent"
  | "requiresUserAction"
  | "requiresPermission"
  | "bug";

export interface RuntimeFailureLocation {
  businessObject: string;
  functionModule: string;
  sourceFilePath?: string;
  sourceLineNumber?: number;
  sourceLineText?: string;
}

export interface RuntimeContextAttribute {
  key: string;
  value: string;
}

export interface RuntimeFailureContext {
  attributes: RuntimeContextAttribute[];
}

export interface RuntimeFailure {
  code: string;
  origin: RuntimeFailureOrigin;
  kind: RuntimeFailureKind;
  nature: RuntimeFailureNature;
  location: RuntimeFailureLocation;
  context: RuntimeFailureContext;
}
