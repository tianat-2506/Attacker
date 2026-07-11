import { describe, expect, it } from "vitest";
import type { BusinessNode } from "../types";
import { accountCanBrowseNetwork, accountCanReadOwnBusiness, accountCanSimulateShock, demoAccounts, recoveryBuyerIdForAccount, scopedBusinessNodesForAccount } from "./demoAccounts";

const nodes: BusinessNode[] = [
  { id: "BIZ-005", name: "Supplier", type: "distributor", province: "Binh Duong", category: "beverage", lat: 0, lng: 0, revenue: 0, capacity: 0, health: 0, risk: 0 },
  { id: "BIZ-009", name: "Buyer SME", type: "retailer", province: "TP.HCM", category: "beverage", lat: 0, lng: 0, revenue: 0, capacity: 0, health: 0, risk: 0 },
  { id: "BIZ-062", name: "Lender", type: "financial_partner", province: "TP.HCM", category: "finance", lat: 0, lng: 0, revenue: 0, capacity: 0, health: 0, risk: 0 }
];

describe("demo account scoping", () => {
  it("keeps SME and supplier profile lists scoped to their own organization", () => {
    const sme = demoAccounts.find((account) => account.id === "sme-submit")!;
    const supplier = demoAccounts.find((account) => account.id === "supplier-admin")!;

    expect(scopedBusinessNodesForAccount(sme, nodes).map((node) => node.id)).toEqual(["BIZ-009"]);
    expect(scopedBusinessNodesForAccount(supplier, nodes).map((node) => node.id)).toEqual(["BIZ-005"]);
    expect(accountCanReadOwnBusiness(sme, "BIZ-005")).toBe(false);
  });

  it("allows network browsing without granting cross-org own-data reads", () => {
    const buyer = demoAccounts.find((account) => account.id === "buyer-admin")!;

    expect(accountCanBrowseNetwork(buyer)).toBe(true);
    expect(scopedBusinessNodesForAccount(buyer, nodes)).toHaveLength(3);
    expect(accountCanReadOwnBusiness(buyer, "BIZ-005")).toBe(false);
    expect(accountCanReadOwnBusiness(buyer, "BIZ-009")).toBe(true);
  });

  it("keeps shock execution narrower than general graph browsing", () => {
    const allowedIds = demoAccounts.filter(accountCanSimulateShock).map((account) => account.id);

    expect(allowedIds).toEqual(["demo-operator", "buyer-admin", "network-analyst", "system-admin"]);
    expect(accountCanSimulateShock(demoAccounts.find((account) => account.id === "sme-submit")!)).toBe(false);
  });

  it("keeps platform operations elevated for demo governance review", () => {
    const systemAdmin = demoAccounts.find((account) => account.id === "system-admin")!;

    expect(accountCanReadOwnBusiness(systemAdmin, "BIZ-062")).toBe(true);
  });

  it("uses the affected SME as the demo-operator recovery buyer", () => {
    const operator = demoAccounts.find((account) => account.id === "demo-operator")!;
    const buyer = demoAccounts.find((account) => account.id === "buyer-admin")!;

    expect(recoveryBuyerIdForAccount(operator, ["BIZ-009", "BIZ-011"])).toBe("BIZ-009");
    expect(recoveryBuyerIdForAccount(operator, ["BIZ-036", "BIZ-009"])).toBe("BIZ-009");
    expect(recoveryBuyerIdForAccount(operator, [])).toBe("BIZ-009");
    expect(recoveryBuyerIdForAccount(buyer, ["BIZ-011"])).toBe("BIZ-009");
  });
});
