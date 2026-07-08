import { describe, expect, it } from "vitest";
import { apiConnectionLabel, authContextLabel, demoBoundaryBanner } from "./demoBoundary";

describe("demoBoundary", () => {
  it("frames full local fallback as intentional competition demo mode", () => {
    const banner = demoBoundaryBanner({
      apiMode: "fallback",
      authContextStatus: "unavailable",
      authContextMismatch: false,
      appMode: "demo"
    });

    expect(banner?.title).toBe("Competition demo mode");
    expect(banner?.message).toContain("synthetic competition dataset");
    expect(banner?.message).toContain("not verified authorization");
    expect(apiConnectionLabel("fallback", "demo")).toBe("Demo dataset active");
    expect(authContextLabel({
      authContextStatus: "unavailable",
      authContextMismatch: false,
      activeActorId: "demo-user",
      appMode: "demo"
    })).toBe("Demo policy simulation");
  });

  it("keeps API fallback honest when actor context is verified", () => {
    const banner = demoBoundaryBanner({
      apiMode: "fallback",
      authContextStatus: "verified",
      authContextMismatch: false,
      appMode: "demo"
    });

    expect(banner?.title).toBe("Competition demo dataset");
    expect(banner?.message).toContain("Authorization denials still fail closed");
  });

  it("uses strict language outside demo mode", () => {
    const banner = demoBoundaryBanner({
      apiMode: "database",
      authContextStatus: "mismatch",
      authContextMismatch: true,
      appMode: "pilot"
    });

    expect(banner?.title).toBe("Verified access context required");
    expect(banner?.message).toContain("Sensitive workflows must stop");
    expect(apiConnectionLabel("fallback", "pilot")).toBe("Backend data unavailable");
    expect(authContextLabel({
      authContextStatus: "mismatch",
      authContextMismatch: true,
      backendActorId: "wrong-actor",
      activeActorId: "demo-user",
      appMode: "pilot"
    })).toBe("Authorization mismatch: backend actor wrong-actor");
  });

  it("stays quiet when backend data and actor context are aligned", () => {
    expect(demoBoundaryBanner({
      apiMode: "database",
      authContextStatus: "verified",
      authContextMismatch: false,
      appMode: "demo"
    })).toBeNull();
    expect(authContextLabel({
      authContextStatus: "verified",
      authContextMismatch: false,
      backendActorId: "demo-user",
      activeActorId: "demo-user",
      authAssurance: "demo-header",
      appMode: "demo"
    })).toBe("demo-header / demo-user");
  });
});
