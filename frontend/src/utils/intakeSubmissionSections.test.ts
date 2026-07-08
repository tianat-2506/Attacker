import { describe, expect, it } from "vitest";
import { intakeSubmissionSections } from "./intakeSubmissionSections";

describe("intakeSubmissionSections", () => {
  it("keeps self-declared evidence metadata out of the submission payload", () => {
    const sections = intakeSubmissionSections(
      {
        revenue: "790000000",
        cash_in: "810000000",
        cash_out: "730000000"
      },
      {
        sku: "SME-BEV-330",
        product_name: "Ready drink 330ml",
        available_capacity: "12000",
        min_order_value: "5000000"
      }
    );

    expect(sections).toEqual({
      financials: {
        revenue: 790000000,
        cash_in: 810000000,
        cash_out: 730000000
      },
      products: [
        {
          sku: "SME-BEV-330",
          product_name: "Ready drink 330ml",
          available_capacity: 12000,
          min_order_value: 5000000
        }
      ]
    });
    expect(sections).not.toHaveProperty("evidence");
  });
});
