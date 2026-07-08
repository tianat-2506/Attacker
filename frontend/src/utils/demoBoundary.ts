export type ApiConnectionMode = "loading" | "database" | "fallback";
export type AuthContextStatus = "loading" | "verified" | "mismatch" | "unavailable";

export interface DemoBoundaryBanner {
  title: string;
  message: string;
}

interface BoundaryInput {
  apiMode: ApiConnectionMode;
  authContextStatus: AuthContextStatus;
  authContextMismatch: boolean;
  appMode?: string;
}

interface AuthLabelInput {
  authContextStatus: AuthContextStatus;
  authContextMismatch: boolean;
  backendActorId?: string | null;
  activeActorId: string;
  authAssurance?: string | null;
  appMode?: string;
}

function isDemoMode(appMode?: string) {
  return (appMode ?? "demo") === "demo";
}

export function demoBoundaryBanner({
  apiMode,
  authContextStatus,
  authContextMismatch,
  appMode
}: BoundaryInput): DemoBoundaryBanner | null {
  const fallbackDataset = apiMode === "fallback";
  const localPolicy = authContextStatus === "unavailable" || authContextMismatch;
  if (!fallbackDataset && !localPolicy) return null;

  if (!isDemoMode(appMode)) {
    return {
      title: "Verified access context required",
      message: "Actor context or backend data is unavailable. Sensitive workflows must stop until verified authorization is restored."
    };
  }

  if (fallbackDataset && localPolicy) {
    return {
      title: "Competition demo mode",
      message: "Using the synthetic competition dataset with local role simulation. Start the backend for persisted audit/auth; this mode is not verified authorization."
    };
  }

  if (fallbackDataset) {
    return {
      title: "Competition demo dataset",
      message: "API data is unavailable, so the synthetic rehearsal dataset is active. Authorization denials still fail closed and are not replaced with fallback data."
    };
  }

  return {
    title: "Demo policy simulation",
    message: "Backend data is connected, but actor context is local or mismatched. Treat navigation as rehearsal permissions, not verified authorization."
  };
}

export function authContextLabel({
  authContextStatus,
  authContextMismatch,
  backendActorId,
  activeActorId,
  authAssurance,
  appMode
}: AuthLabelInput): string {
  if (authContextStatus === "loading") return "Checking backend actor context";
  if (!isDemoMode(appMode)) {
    if (authContextStatus === "unavailable") return "Verified authorization unavailable";
    if (authContextMismatch) return `Authorization mismatch: backend actor ${backendActorId ?? "unknown"}`;
  } else {
    if (authContextStatus === "unavailable") return "Demo policy simulation";
    if (authContextMismatch) return `Demo policy simulation: backend actor ${backendActorId ?? "unknown"}`;
  }
  return `${authAssurance ?? "demo-header"} / ${backendActorId ?? activeActorId}`;
}

export function apiConnectionLabel(apiMode: ApiConnectionMode, appMode?: string): string {
  if (apiMode === "database") return "SQLite API connected";
  if (apiMode === "loading") return "Connecting API";
  return isDemoMode(appMode) ? "Demo dataset active" : "Backend data unavailable";
}
