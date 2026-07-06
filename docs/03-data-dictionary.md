# Data Dictionary

MVP co 4 dataset bat buoc va 1 dataset optional. Du lieu demo la synthetic, seed on dinh, co logic F&B/FMCG mien Nam.

## 1. Dataset `businesses`

| Field | Type | Required | Validation | Vi du |
| --- | --- | --- | --- | --- |
| `business_id` | string | yes | Unique, pattern `BIZ-###` | `BIZ-023` |
| `name` | string | yes | 3-80 chars | `Dai Tin Distribution` |
| `type` | enum | yes | `manufacturer`, `distributor`, `wholesaler`, `retailer`, `financial_partner` | `distributor` |
| `industry` | string | yes | MVP: `F&B/FMCG` | `F&B/FMCG` |
| `product_category` | string | yes | In taxonomy | `packaged_food` |
| `province` | enum | yes | `TP.HCM`, `Binh Duong`, `Dong Nai`, `Lam Dong` | `Binh Duong` |
| `lat` | number | yes | Vietnam range, mien Nam bbox | `10.9804` |
| `lng` | number | yes | Vietnam range, mien Nam bbox | `106.6519` |
| `scale` | enum | yes | `micro`, `small`, `medium`, `large` | `medium` |
| `monthly_revenue` | number | yes | VND, >=0 | `3200000000` |
| `capacity` | number | yes | Units/month, >=0 | `90000` |
| `financial_health_score` | number | yes | 0-100 | `72` |
| `supply_risk_score` | number | yes | 0-100 | `58` |

Suggested seed distribution:

- 4 manufacturers.
- 16 distributors.
- 14 wholesalers/agents.
- 26 SME retailers.
- 2 financial partners.
- Tong: 62 businesses.

## 2. Dataset `supply_edges`

| Field | Type | Required | Validation | Vi du |
| --- | --- | --- | --- | --- |
| `edge_id` | string | yes | Unique, pattern `EDGE-###` | `EDGE-041` |
| `source_id` | string | yes | FK -> `businesses.business_id` | `BIZ-005` |
| `target_id` | string | yes | FK -> `businesses.business_id`; source != target | `BIZ-023` |
| `product` | string | yes | Non-empty | `sua hat dong hop` |
| `product_category` | string | yes | Match product taxonomy | `beverage` |
| `monthly_volume` | number | yes | Units/month, >0 | `12000` |
| `lead_time_days` | number | yes | 0-30 | `2` |
| `transport_cost` | number | yes | VND/month, >=0 | `18000000` |
| `reliability` | number | yes | 0-1 | `0.93` |
| `payment_term_days` | number | yes | 0, 7, 15, 30, 45, 60 | `30` |

Suggested seed:

- 120-150 directed edges.
- Manufacturer -> distributor: 35%.
- Distributor -> wholesaler/retailer: 50%.
- Wholesaler -> retailer: 15%.

## 3. Dataset `financials`

| Field | Type | Required | Validation | Vi du |
| --- | --- | --- | --- | --- |
| `business_id` | string | yes | FK -> businesses | `BIZ-023` |
| `month` | string | yes | `YYYY-MM`, 12 thang lien tuc | `2026-05` |
| `cash_in` | number | yes | VND, >=0 | `2800000000` |
| `cash_out` | number | yes | VND, >=0 | `3050000000` |
| `revenue` | number | yes | VND, >=0 | `3300000000` |
| `debt` | number | yes | VND, >=0 | `1200000000` |
| `accounts_receivable` | number | yes | VND, >=0 | `850000000` |
| `accounts_payable` | number | yes | VND, >=0 | `640000000` |
| `inventory_value` | number | yes | VND, >=0 | `910000000` |
| `late_payment_rate` | number | yes | 0-1 | `0.22` |
| `delivery_delay_rate` | number | yes | 0-1 | `0.14` |

Risk demo seed:

- Chon 1 distributor target co `cash_in` giam 3 thang lien tiep.
- `late_payment_rate` tang tu 0.08 len 0.24.
- `inventory_value/revenue` tang bat thuong.
- `delivery_delay_rate` tang tu 0.05 len 0.16.

## 4. Dataset `products`

| Field | Type | Required | Validation | Vi du |
| --- | --- | --- | --- | --- |
| `business_id` | string | yes | FK -> businesses | `BIZ-005` |
| `sku` | string | yes | Unique within business | `SKU-SUAHAT-1L` |
| `product_name` | string | yes | Non-empty | `Sua hat dong hop 1L` |
| `category` | string | yes | Product taxonomy | `beverage` |
| `specification` | string | yes | Human-readable spec | `UHT, 1L, khong duong` |
| `available_capacity` | number | yes | Units/month, >=0 | `45000` |
| `min_order_value` | number | yes | VND, >=0 | `50000000` |
| `price_range` | string | yes | `low`, `mid`, `premium` hoac range VND | `mid` |
| `certifications` | string[] | no | From controlled list | `["HACCP", "ISO 22000"]` |

Product taxonomy MVP:

- `beverage`: sua hat, tra dong chai, nuoc trai cay.
- `packaged_food`: banh snack, ngu coc, mi/an lien.
- `processed_agri`: ca phe rang xay, trai cay say, rau cu dong goi.
- `cold_chain_food`: sua chua, thuc pham dong lanh.

## 5. Optional dataset `invoice_verifications`

| Field | Type | Required | Validation | Vi du |
| --- | --- | --- | --- | --- |
| `invoice_id` | string | yes | Unique | `INV-0241` |
| `seller_id` | string | yes | FK -> businesses | `BIZ-005` |
| `buyer_id` | string | yes | FK -> businesses | `BIZ-023` |
| `amount` | number | yes | VND, >0 | `240000000` |
| `issue_date` | string | yes | ISO date | `2026-06-05` |
| `due_date` | string | yes | ISO date, >= issue_date | `2026-07-05` |
| `invoice_hash` | string | yes | SHA-256 hex | `b6c...` |
| `funding_status` | enum | yes | `unfunded`, `pending`, `funded`, `repaid`, `rejected` | `funded` |
| `confirmed_by` | string[] | yes | buyer/seller/logistics/finance | `["buyer", "seller"]` |

Nguon hash: [NIST FIPS 180-4 Secure Hash Standard](https://csrc.nist.gov/pubs/fips/180-4/upd1/final).

## 6. Sample synthetic businesses

| business_id | name | type | province | category | revenue/month | capacity | health | risk |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| BIZ-001 | Highland Agri Foods | manufacturer | Lam Dong | processed_agri | 5200000000 | 160000 | 82 | 24 |
| BIZ-002 | Saigon NutriDrink | manufacturer | TP.HCM | beverage | 7800000000 | 220000 | 78 | 31 |
| BIZ-003 | Dong Nai Packaged Food | manufacturer | Dong Nai | packaged_food | 6100000000 | 180000 | 74 | 36 |
| BIZ-004 | Binh Duong Cold Chain Foods | manufacturer | Binh Duong | cold_chain_food | 6900000000 | 140000 | 80 | 28 |
| BIZ-005 | Dai Tin Distribution | distributor | Binh Duong | beverage | 3400000000 | 95000 | 47 | 76 |
| BIZ-006 | Mekong Fresh Distributor | distributor | TP.HCM | processed_agri | 2900000000 | 78000 | 68 | 42 |
| BIZ-007 | An Phu FMCG Hub | distributor | Dong Nai | packaged_food | 4100000000 | 105000 | 71 | 39 |
| BIZ-008 | Dalat Pure Foods | distributor | Lam Dong | processed_agri | 2600000000 | 72000 | 75 | 33 |
| BIZ-009 | Thu Duc Retail Mart | retailer | TP.HCM | beverage | 620000000 | 8500 | 64 | 51 |
| BIZ-010 | Bien Hoa Mini Market | retailer | Dong Nai | packaged_food | 480000000 | 7000 | 59 | 57 |
| BIZ-011 | Di An Convenience | retailer | Binh Duong | beverage | 530000000 | 7600 | 62 | 54 |
| BIZ-012 | Bao Loc Specialty Store | retailer | Lam Dong | processed_agri | 390000000 | 5200 | 70 | 41 |

Trong seed that, mo rong thanh 62 doanh nghiep bang cung pattern tren. Du lieu can co file generator de dam bao deterministic seed.

## 7. Full synthetic seed inventory - 62 businesses

Bang nay la danh sach seed de team co the sinh CSV day du trong buoc skeleton code. Cac chi so doanh thu/capacity/health/risk se duoc generate deterministic theo type, province va scenario.

| business_id | name | type | province | product_category | scale |
| --- | --- | --- | --- | --- | --- |
| BIZ-001 | Highland Agri Foods | manufacturer | Lam Dong | processed_agri | large |
| BIZ-002 | Saigon NutriDrink | manufacturer | TP.HCM | beverage | large |
| BIZ-003 | Dong Nai Packaged Food | manufacturer | Dong Nai | packaged_food | large |
| BIZ-004 | Binh Duong Cold Chain Foods | manufacturer | Binh Duong | cold_chain_food | medium |
| BIZ-005 | Dai Tin Distribution | distributor | Binh Duong | beverage | medium |
| BIZ-006 | Mekong Fresh Distributor | distributor | TP.HCM | processed_agri | medium |
| BIZ-007 | An Phu FMCG Hub | distributor | Dong Nai | packaged_food | medium |
| BIZ-008 | Dalat Pure Foods | distributor | Lam Dong | processed_agri | small |
| BIZ-009 | Thu Duc Retail Mart | retailer | TP.HCM | beverage | small |
| BIZ-010 | Bien Hoa Mini Market | retailer | Dong Nai | packaged_food | micro |
| BIZ-011 | Di An Convenience | retailer | Binh Duong | beverage | small |
| BIZ-012 | Bao Loc Specialty Store | retailer | Lam Dong | processed_agri | micro |
| BIZ-013 | Gia Dinh Beverage Supply | distributor | TP.HCM | beverage | medium |
| BIZ-014 | Tan Uyen FMCG Distribution | distributor | Binh Duong | packaged_food | medium |
| BIZ-015 | Xuan Loc Agri Trade | distributor | Dong Nai | processed_agri | small |
| BIZ-016 | Duc Trong Food Link | distributor | Lam Dong | processed_agri | small |
| BIZ-017 | Song Than Cold Logistics | distributor | Binh Duong | cold_chain_food | medium |
| BIZ-018 | Nha Be Grocery Supply | distributor | TP.HCM | packaged_food | medium |
| BIZ-019 | Trang Bom Beverage Link | distributor | Dong Nai | beverage | small |
| BIZ-020 | Da Lat Dairy Route | distributor | Lam Dong | cold_chain_food | small |
| BIZ-021 | Cho Lon Wholesale Foods | wholesaler | TP.HCM | packaged_food | small |
| BIZ-022 | Go Vap Beverage Agent | wholesaler | TP.HCM | beverage | small |
| BIZ-023 | Thu Duc Agri Agent | wholesaler | TP.HCM | processed_agri | small |
| BIZ-024 | Ben Cat FMCG Wholesale | wholesaler | Binh Duong | packaged_food | small |
| BIZ-025 | Thuan An Beverage Agent | wholesaler | Binh Duong | beverage | small |
| BIZ-026 | Bau Bang Cold Agent | wholesaler | Binh Duong | cold_chain_food | micro |
| BIZ-027 | Long Thanh Food Wholesale | wholesaler | Dong Nai | packaged_food | small |
| BIZ-028 | Nhon Trach Beverage Agent | wholesaler | Dong Nai | beverage | small |
| BIZ-029 | Tan Phu Agri Wholesale | wholesaler | Dong Nai | processed_agri | micro |
| BIZ-030 | Da Lat Specialty Agent | wholesaler | Lam Dong | processed_agri | small |
| BIZ-031 | Bao Loc Coffee Agent | wholesaler | Lam Dong | processed_agri | micro |
| BIZ-032 | Duc Trong Dairy Agent | wholesaler | Lam Dong | cold_chain_food | small |
| BIZ-033 | Phu Nhuan Snack Agent | wholesaler | TP.HCM | packaged_food | micro |
| BIZ-034 | Bien Hoa Cold Chain Agent | wholesaler | Dong Nai | cold_chain_food | small |
| BIZ-035 | District 1 Mini Mart | retailer | TP.HCM | beverage | micro |
| BIZ-036 | District 7 Family Store | retailer | TP.HCM | packaged_food | micro |
| BIZ-037 | Binh Thanh Organic Shop | retailer | TP.HCM | processed_agri | micro |
| BIZ-038 | Tan Phu Convenience | retailer | TP.HCM | beverage | micro |
| BIZ-039 | Hoc Mon Grocery | retailer | TP.HCM | packaged_food | micro |
| BIZ-040 | Thu Duc Milk Corner | retailer | TP.HCM | cold_chain_food | micro |
| BIZ-041 | Thuan An Family Mart | retailer | Binh Duong | beverage | micro |
| BIZ-042 | Ben Cat Grocery | retailer | Binh Duong | packaged_food | micro |
| BIZ-043 | Tan Uyen Organic Store | retailer | Binh Duong | processed_agri | micro |
| BIZ-044 | Di An Milk Store | retailer | Binh Duong | cold_chain_food | micro |
| BIZ-045 | Bau Bang Mini Mart | retailer | Binh Duong | packaged_food | micro |
| BIZ-046 | Thu Dau Mot Beverage Shop | retailer | Binh Duong | beverage | small |
| BIZ-047 | Bien Hoa Family Foods | retailer | Dong Nai | packaged_food | micro |
| BIZ-048 | Long Khanh Coffee Store | retailer | Dong Nai | processed_agri | micro |
| BIZ-049 | Nhon Trach Mini Mart | retailer | Dong Nai | beverage | micro |
| BIZ-050 | Long Thanh Cold Foods | retailer | Dong Nai | cold_chain_food | micro |
| BIZ-051 | Trang Bom Grocery | retailer | Dong Nai | packaged_food | micro |
| BIZ-052 | Xuan Loc Agri Shop | retailer | Dong Nai | processed_agri | micro |
| BIZ-053 | Da Lat Farm Mart | retailer | Lam Dong | processed_agri | small |
| BIZ-054 | Bao Loc Coffee Corner | retailer | Lam Dong | processed_agri | micro |
| BIZ-055 | Duc Trong Family Store | retailer | Lam Dong | packaged_food | micro |
| BIZ-056 | Lam Ha Beverage Shop | retailer | Lam Dong | beverage | micro |
| BIZ-057 | Don Duong Dairy Store | retailer | Lam Dong | cold_chain_food | micro |
| BIZ-058 | Da Huoai Specialty Mart | retailer | Lam Dong | processed_agri | micro |
| BIZ-059 | Cat Tien Grocery | retailer | Lam Dong | packaged_food | micro |
| BIZ-060 | Lac Duong Farm Goods | retailer | Lam Dong | processed_agri | micro |
| BIZ-061 | VietWorking Capital Partner | financial_partner | TP.HCM | finance | medium |
| BIZ-062 | Saigon Invoice Finance | financial_partner | TP.HCM | finance | medium |

## 8. Edge generation plan - 120 directed edges

| Edge group | Count | Pattern |
| --- | ---: | --- |
| Manufacturer -> distributor | 24 | Moi manufacturer cap cho 5-7 distributors theo category |
| Distributor -> wholesaler | 32 | Moi distributor co 1-3 wholesaler downstream |
| Distributor -> retailer | 44 | Dai Tin Distribution co 12 SME beverage downstream de lam shock scenario |
| Wholesaler -> retailer | 20 | Bo sung local redundancy va multi-hop impact |

Default shock node:

- `BIZ-005 Dai Tin Distribution`.
- Product category: `beverage`.
- Minimum downstream affected SME: 12.
- Expected impact: 70,000-85,000 units/month at risk.

## 9. Validation checklist

- `business_id` unique va duoc tham chieu dung trong edges, financials, products.
- Khong co `lat/lng` ngoai mien Nam.
- Edge khong tao self-loop.
- Moi business co it nhat 12 dong financials.
- `reliability`, `late_payment_rate`, `delivery_delay_rate` nam trong 0-1.
- Products cua supplier phai phu hop category de match.
- Distributor shock target phai co it nhat 5 downstream retailers de demo co tac dong.

Nguon data modeling va ETL: [PostgreSQL docs](https://www.postgresql.org/docs/current/), [IBM ETL](https://www.ibm.com/think/topics/etl), [GeoJSON RFC 7946](https://datatracker.ietf.org/doc/html/rfc7946).
