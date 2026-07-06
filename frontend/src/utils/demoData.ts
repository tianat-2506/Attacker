import type { BusinessNode, Recommendation, RiskDriver, ShockState, SupplyEdge } from "../types";

export const businesses: BusinessNode[] = [
  { id: "BIZ-002", name: "Saigon NutriDrink", type: "manufacturer", province: "TP.HCM", category: "beverage", lat: 10.7769, lng: 106.7009, revenue: 7.8, capacity: 220000, health: 78, risk: 31 },
  { id: "BIZ-005", name: "Dai Tin Distribution", type: "distributor", province: "Binh Duong", category: "beverage", lat: 10.9951, lng: 106.6792, revenue: 3.4, capacity: 95000, health: 43, risk: 78 },
  { id: "BIZ-007", name: "An Phu FMCG Hub", type: "distributor", province: "Dong Nai", category: "beverage", lat: 10.9467, lng: 106.8243, revenue: 4.1, capacity: 105000, health: 72, risk: 38 },
  { id: "BIZ-013", name: "Gia Dinh Beverage Supply", type: "distributor", province: "TP.HCM", category: "beverage", lat: 10.8032, lng: 106.696, revenue: 3.6, capacity: 98000, health: 70, risk: 42 },
  { id: "BIZ-019", name: "Trang Bom Beverage Link", type: "distributor", province: "Dong Nai", category: "beverage", lat: 10.9537, lng: 107.0067, revenue: 1.1, capacity: 43000, health: 68, risk: 45 },
  { id: "BIZ-022", name: "Go Vap Beverage Agent", type: "wholesaler", province: "TP.HCM", category: "beverage", lat: 10.8387, lng: 106.6653, revenue: 0.9, capacity: 34000, health: 66, risk: 48 },
  { id: "BIZ-025", name: "Thuan An Beverage Agent", type: "wholesaler", province: "Binh Duong", category: "beverage", lat: 10.9316, lng: 106.711, revenue: 0.86, capacity: 30000, health: 63, risk: 52 },
  { id: "BIZ-028", name: "Nhon Trach Beverage Agent", type: "wholesaler", province: "Dong Nai", category: "beverage", lat: 10.6952, lng: 106.8831, revenue: 0.8, capacity: 28500, health: 65, risk: 49 },
  { id: "BIZ-009", name: "Thu Duc Retail Mart", type: "retailer", province: "TP.HCM", category: "beverage", lat: 10.8494, lng: 106.7537, revenue: 0.62, capacity: 8500, health: 64, risk: 51 },
  { id: "BIZ-011", name: "Di An Convenience", type: "retailer", province: "Binh Duong", category: "beverage", lat: 10.9068, lng: 106.7694, revenue: 0.53, capacity: 7600, health: 62, risk: 54 },
  { id: "BIZ-035", name: "District 1 Mini Mart", type: "retailer", province: "TP.HCM", category: "beverage", lat: 10.7758, lng: 106.7004, revenue: 0.42, capacity: 6200, health: 61, risk: 53 },
  { id: "BIZ-038", name: "Tan Phu Convenience", type: "retailer", province: "TP.HCM", category: "beverage", lat: 10.7902, lng: 106.6282, revenue: 0.39, capacity: 5900, health: 60, risk: 55 },
  { id: "BIZ-041", name: "Thuan An Family Mart", type: "retailer", province: "Binh Duong", category: "beverage", lat: 10.933, lng: 106.7122, revenue: 0.44, capacity: 6800, health: 58, risk: 57 },
  { id: "BIZ-046", name: "Thu Dau Mot Beverage Shop", type: "retailer", province: "Binh Duong", category: "beverage", lat: 10.9801, lng: 106.6555, revenue: 0.8, capacity: 12000, health: 63, risk: 50 },
  { id: "BIZ-049", name: "Nhon Trach Mini Mart", type: "retailer", province: "Dong Nai", category: "beverage", lat: 10.6957, lng: 106.8844, revenue: 0.41, capacity: 6100, health: 59, risk: 56 },
  { id: "BIZ-056", name: "Lam Ha Beverage Shop", type: "retailer", province: "Lam Dong", category: "beverage", lat: 11.801, lng: 108.2388, revenue: 0.36, capacity: 5200, health: 64, risk: 47 }
];

export const edges: SupplyEdge[] = [
  { id: "EDGE-001", sourceId: "BIZ-002", targetId: "BIZ-005", category: "beverage", volume: 68000, leadTimeDays: 2, reliability: 0.93 },
  { id: "EDGE-002", sourceId: "BIZ-002", targetId: "BIZ-007", category: "beverage", volume: 52000, leadTimeDays: 2, reliability: 0.95 },
  { id: "EDGE-003", sourceId: "BIZ-002", targetId: "BIZ-013", category: "beverage", volume: 48000, leadTimeDays: 1, reliability: 0.91 },
  { id: "EDGE-004", sourceId: "BIZ-002", targetId: "BIZ-019", category: "beverage", volume: 26000, leadTimeDays: 3, reliability: 0.89 },
  { id: "EDGE-055", sourceId: "BIZ-005", targetId: "BIZ-009", category: "beverage", volume: 9200, leadTimeDays: 2, reliability: 0.86 },
  { id: "EDGE-056", sourceId: "BIZ-005", targetId: "BIZ-011", category: "beverage", volume: 8400, leadTimeDays: 2, reliability: 0.83 },
  { id: "EDGE-057", sourceId: "BIZ-005", targetId: "BIZ-035", category: "beverage", volume: 7100, leadTimeDays: 3, reliability: 0.82 },
  { id: "EDGE-058", sourceId: "BIZ-005", targetId: "BIZ-038", category: "beverage", volume: 6900, leadTimeDays: 3, reliability: 0.8 },
  { id: "EDGE-059", sourceId: "BIZ-005", targetId: "BIZ-041", category: "beverage", volume: 7800, leadTimeDays: 2, reliability: 0.81 },
  { id: "EDGE-060", sourceId: "BIZ-005", targetId: "BIZ-046", category: "beverage", volume: 9600, leadTimeDays: 1, reliability: 0.84 },
  { id: "EDGE-061", sourceId: "BIZ-005", targetId: "BIZ-049", category: "beverage", volume: 6500, leadTimeDays: 4, reliability: 0.79 },
  { id: "EDGE-062", sourceId: "BIZ-005", targetId: "BIZ-056", category: "beverage", volume: 6100, leadTimeDays: 5, reliability: 0.78 },
  { id: "EDGE-080", sourceId: "BIZ-007", targetId: "BIZ-009", category: "beverage", volume: 5200, leadTimeDays: 2, reliability: 0.93 },
  { id: "EDGE-081", sourceId: "BIZ-013", targetId: "BIZ-035", category: "beverage", volume: 4400, leadTimeDays: 1, reliability: 0.92 },
  { id: "EDGE-082", sourceId: "BIZ-019", targetId: "BIZ-049", category: "beverage", volume: 3900, leadTimeDays: 2, reliability: 0.9 },
  { id: "EDGE-083", sourceId: "BIZ-022", targetId: "BIZ-038", category: "beverage", volume: 2400, leadTimeDays: 1, reliability: 0.89 },
  { id: "EDGE-084", sourceId: "BIZ-025", targetId: "BIZ-041", category: "beverage", volume: 2600, leadTimeDays: 1, reliability: 0.88 }
];

export const riskDrivers: RiskDriver[] = [
  { label: "Cashflow risk", value: 84, note: "Cash inflow giam trong 3 thang gan nhat" },
  { label: "Late payment", value: 96, note: "Ty le thanh toan tre tang len 24%" },
  { label: "Delivery delay", value: 80, note: "Ty le giao tre tang len 16%" }
];

export const defaultShock: ShockState = {
  active: false,
  shockNodeId: "BIZ-005",
  affectedNodeIds: ["BIZ-009", "BIZ-011", "BIZ-035", "BIZ-038", "BIZ-041", "BIZ-046", "BIZ-049", "BIZ-056"],
  affectedEdgeIds: ["EDGE-055", "EDGE-056", "EDGE-057", "EDGE-058", "EDGE-059", "EDGE-060", "EDGE-061", "EDGE-062"],
  affectedSmeCount: 12,
  monthlyVolumeAtRisk: 78000,
  revenueAtRisk: 1872000000,
  avgStockoutDays: 3.8
};

export const recommendations: Recommendation[] = [
  {
    supplierId: "BIZ-007",
    supplierName: "An Phu FMCG Hub",
    score: 86,
    leadTimeDays: 2,
    reasons: ["Dung spec UHT 1L", "Con capacity 28,000 units/month", "Reliability 93%", "Chap nhan net-30"],
    components: { productFit: 100, capacityFit: 92, distance: 86, financialHealth: 72, reliability: 93, paymentTerms: 100 }
  },
  {
    supplierId: "BIZ-013",
    supplierName: "Gia Dinh Beverage Supply",
    score: 82,
    leadTimeDays: 1,
    reasons: ["Gan cum TP.HCM", "Lead time 1 ngay", "Health score 70", "Gia mid-range"],
    components: { productFit: 100, capacityFit: 88, distance: 91, financialHealth: 70, reliability: 92, paymentTerms: 70 }
  },
  {
    supplierId: "BIZ-019",
    supplierName: "Trang Bom Beverage Link",
    score: 76,
    leadTimeDays: 2,
    reasons: ["Phu hop Dong Nai", "Capacity du bu mot phan", "Reliability 90%", "Risk filter dat"],
    components: { productFit: 100, capacityFit: 73, distance: 72, financialHealth: 68, reliability: 90, paymentTerms: 70 }
  }
];
