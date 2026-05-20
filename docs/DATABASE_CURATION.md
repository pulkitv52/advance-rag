# Database Curation

The curated registry layer consolidates beneficiary enrollment, payout detail, and audit decisions from the raw `srsadmin` source tables.

## Objects
- `srsadmin.master_beneficiary_profile`
  - canonical enrollment record at `uid + scheme_beneficiary_id`
  - includes personal fields, scheme fields, RC enrichment, and aggregated payout summary
- `srsadmin.master_beneficiary_transactions`
  - one row per payout event
  - includes `uid`, `scheme_id`, `scheme_beneficiary_id`, installment metadata, amount, and transaction reference
- `srsadmin.master_beneficiary_full_view`
  - left join of profile to transaction detail for ad hoc analysis and pgAdmin inspection
- `srsadmin.master_beneficiary_skipped_entries`
  - audit table for invalid rows, duplicate losers, RC ambiguity, and unmatched transactions
- `srsadmin.master_beneficiary_dataset`
  - compatibility table preserved for current backend reads

## Canonical Key
- Canonical beneficiary enrollment key: `uid + scheme_beneficiary_id`
- `scheme_id` remains mandatory business context and is stored on every curated row

## Deduplication
Duplicate beneficiary rows are ranked by:
1. latest `modify_ts`
2. latest `entry_ts`
3. latest `approved_date`
4. highest completeness score
5. source priority and `sl_no`

Only the winning row is retained in `master_beneficiary_profile`. Losing rows are written to `master_beneficiary_skipped_entries`.

## Skip Reasons
The audit table uses these reason codes:
- `MISSING_UID`
- `MISSING_SCHEME_BENEFICIARY_ID`
- `DUPLICATE_LOSER`
- `CONFLICTING_SCHEME_ID`
- `AMBIGUOUS_RC_MATCH`
- `NO_BENEFICIARY_MATCH_FOR_TRANSACTION`
- `INVALID_KEY_COMBINATION`
- `CONFLICTING_PERSONAL_DATA`

## Recommended Reads
- Current backend compatibility: read `srsadmin.master_beneficiary_dataset`
- Curated beneficiary queries: read `srsadmin.master_beneficiary_profile`
- Detailed payout inspection: read `srsadmin.master_beneficiary_full_view`
- Data quality and exception review: read `srsadmin.master_beneficiary_skipped_entries`
