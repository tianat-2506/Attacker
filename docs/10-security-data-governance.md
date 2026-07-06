# Security and Data Governance

## 1. Du lieu nhay cam

| Data | Vi sao nhay cam | Cach xu ly MVP | Cach xu ly pilot/production |
| --- | --- | --- | --- |
| Danh sach supplier/customer | Loi the canh tranh, bi loi dung de tiep can truc tiep | Synthetic/masked | RBAC, consent, edge masking |
| Supply edges va volume | Lo quan he thuong mai va quy mo mua ban | Range/aggregate | Attribute-level access control, audit logs |
| Financials/cashflow | Du lieu song con cua SME | Synthetic | Encryption, least privilege, consent, retention |
| Invoices | Co the bi dung cho double financing/fraud | Hash + simulated status | Raw invoice off-chain, encrypted storage, audit |
| Contact info | PII/business confidential | Khong can trong MVP | Consent before reveal, data minimization |
| API keys/secrets | Mat secret co the lo he thong | Khong commit | Secret manager, rotation |

Nguon: [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/), [NIST Privacy Framework](https://www.nist.gov/privacy-framework), [OWASP Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html).

## 2. Data ownership and consent

Quyen so huu:

- SME so huu financial snapshots, invoices, purchase demand.
- Supplier/distributor so huu product capacity, terms, certifications va performance private.
- Platform so huu derived risk/matching signals nhung phai giai thich nguon/logic.
- Financial partner chi xem du lieu da duoc SME consent.

Consent model:

| Action | Consent required |
| --- | --- |
| Xem graph aggregate/masked | No trong demo/pilot public view |
| Xem ten supplier/customer that | Mutual consent |
| Chia se financial summary voi financial partner | SME consent |
| Verify invoice voi buyer/seller | Buyer + seller confirmation |
| Dung data de train ML | Explicit consent + anonymization policy |

## 3. RBAC

| Role | Allowed | Denied |
| --- | --- | --- |
| `sme_user` | Own profile, own suppliers, masked recommendations | Other SME financials, full graph |
| `supplier_user` | Own products/capacity, accepted leads | Competitor customer list |
| `financial_partner` | Consented risk summary/invoice status | Raw graph without consent |
| `admin` | Synthetic/admin operations | Production direct DB export without audit |
| `demo_operator` | Trigger shock, reset seed | Real user data |

## 4. Graph masking

MVP/pilot masking levels:

1. `public_aggregate`: chi hien node count, province, type, risk distribution.
2. `masked_business`: hien alias `Distributor A`, category, province, approximate size.
3. `consented_match`: hien ten that, contact channel va proposed PO details.
4. `admin_audit`: full synthetic/admin view.

Implementation notes:

- API co query `masked=true` default.
- Field `display_name` khac `name`.
- Edge `monthly_volume` hien range: `0-5k`, `5k-20k`, `20k+` neu chua co consent.
- Lat/lng co the jitter/aggregate theo province trong pilot public view.

## 5. Encryption and transport

- MVP local: khong dung data that, nhung van khong commit secrets.
- Production: TLS for all API calls, HSTS tren frontend.
- At-rest encryption cho database/storage cua financials/invoices.
- Hash invoices bang SHA-256 tren canonical JSON; hash khong thay the encryption.
- Secrets dung secret manager; `.env` chi cho local dev.

Nguon hash: [NIST FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final).

## 6. Audit logging

Audit events:

- `BUSINESS_DETAIL_VIEWED`
- `FINANCIAL_SUMMARY_VIEWED`
- `INVOICE_VERIFICATION_VIEWED`
- `SUPPLIER_INTRO_REQUESTED`
- `CONSENT_GRANTED`
- `CONSENT_REVOKED`
- `EXPORT_REQUESTED`
- `RISK_SCORE_RECALCULATED`

Audit fields:

```json
{
  "event_id": "AUD-001",
  "event_type": "FINANCIAL_SUMMARY_VIEWED",
  "actor_id": "USER-010",
  "actor_role": "financial_partner",
  "subject_business_id": "BIZ-009",
  "purpose": "working_capital_review",
  "timestamp": "2026-06-22T10:00:00Z",
  "request_id": "req_123"
}
```

## 7. Data retention and deletion

MVP:

- Synthetic data can be reset anytime.

Pilot:

- Keep raw imported files for limited period, e.g. 30-90 days.
- Keep derived aggregated metrics longer if anonymized.
- Support deletion/revocation request for pilot participants.
- Keep audit logs for compliance window, but minimize sensitive payload.

## 8. Fraud and KYB/KYC notes

MVP can show fraud flags only as simulation:

- Duplicate invoice hash.
- Same invoice amount/date/buyer/seller with different ID.
- Seller/buyer mismatch confirmation.
- Sudden spike in invoice volume.

Production needs KYB/KYC, sanctions screening where applicable, invoice authenticity checks and partner financial institution underwriting. This product should not present itself as a lender unless it has the legal/compliance structure to do so.

## 9. Security checklist before pilot

- [ ] No secrets in repo.
- [ ] `.env.example` only contains placeholders.
- [ ] RBAC defined and tested.
- [ ] Graph masking default on.
- [ ] Consent table and audit log implemented.
- [ ] TLS on deployed API.
- [ ] Error responses do not leak stack traces.
- [ ] Dependency scanning in CI.
- [ ] Data processing agreement template ready for pilot partners.
- [ ] Incident response contact and runbook defined.

## 10. Threats and mitigations

| Threat | Impact | Mitigation |
| --- | --- | --- |
| Supplier list scraping | Mat loi the canh tranh | Rate limit, auth, masking, pagination, anomaly logs |
| Unauthorized financial access | Mat niem tin, legal risk | RBAC, consent, audit, encryption |
| Prompt/AI explanation hallucination | Giai thich sai | Template-based explanation in MVP, source drivers only |
| Double financing bypass | Financial loss | Hash + multi-party confirmation + partner underwriting |
| Poisoned data | Score sai | Data validation, lineage, manual review |
| Secret leak | System compromise | Secret manager, rotation, no hard-code |
