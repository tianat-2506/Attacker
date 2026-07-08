const numericProductFields = new Set(["available_capacity", "min_order_value"]);

export function intakeSubmissionSections(
  financials: Record<string, string>,
  product: Record<string, string>
) {
  return {
    financials: Object.fromEntries(
      Object.entries(financials).map(([key, value]) => [key, Number(value)])
    ),
    products: [
      Object.fromEntries(
        Object.entries(product).map(([key, value]) => [
          key,
          numericProductFields.has(key) ? Number(value) : value
        ])
      )
    ]
  };
}
