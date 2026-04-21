# SRSDB Dump Overview

Source dump: `srsdb.dump` (PostgreSQL custom dump, pg_dump 16.4)

## 1) What this dump is

- Database name in dump metadata: `srsdb`.
- Dump format: PostgreSQL `custom` format.
- Dumped from PostgreSQL `16.4`.
- Archive TOC entries: `1776`.

## 2) High-level object counts (from TOC)

- `SCHEMA`: 1 (`srsadmin`; `public` already exists by default).
- `FUNCTION`: 2
- `TABLE` DDL entries: 175 physical tables.
- `TABLE DATA` entries: 168 tables with data loaded.
- `SEQUENCE`: 21
- `INDEX`: 1026
- `CONSTRAINT`: 150
- `ACL` entries: 52
- `ATTACH` entries: 168 (partition attachments)

## 3) Schema layout

- Two main schemas hold table objects:
- `public`: 50 table objects, 48 table-data loads.
- `srsadmin`: 125 table objects, 120 table-data loads.

## 4) Core data model

- Main domain appears to be welfare/beneficiary + payment transactions.
- Data is heavily partitioned by district code (`lgd_district_code`) using list partitioning.

Primary table families:

- `public.swasthya_sathi_beneficiary` + district partitions (`_000`, `_303`, ... `_704`).
- `public.swasthya_sathi_transaction_2526` + district partitions.
- `srsadmin.swasthya_sathi_beneficiary` + district partitions.
- `srsadmin.swasthya_sathi_transaction_2526` + district partitions.
- `srsadmin.rc_beneficiary` + district partitions.
- `srsadmin.scheme_beneficiary_cash` + district partitions.
- `srsadmin.scheme_transaction_cash_2526` + district partitions.
- Mask/helper partition tables also exist (for example `*_mask_000`).

## 5) Masking/anonymization evidence

- Functions present:
- `srsadmin.mask_mobile_digits(text)`
- `srsadmin.transform_fullname_words(text)`

These functions exist in schema, but dump data rows include human-readable names in sampled partitions (not obviously transformed during restore itself).

## 6) Keys and indexing pattern

- Most partition families define composite primary keys at parent + child levels.
- Example beneficiary PK pattern:
- `(scheme_id, scheme_beneficiary_id, lgd_district_code)`
- Transaction PK pattern includes year/month (and api ID for some tables).
- Large index footprint (`1026`) indicates read-heavy lookup use cases.

## 7) Access control pattern

- ACL entries show broad grants around `srsadmin` objects (tables/sequences).
- Object owner is mostly `postgres`.

## 8) Practical interpretation

- This is a district-partitioned operational registry dump.
- `public` contains core Swasthya Sathi beneficiary/transaction data.
- `srsadmin` contains admin/masked/derived mirrors and cash-scheme tables.
- Partitioning strategy is designed for district-wise ingestion and query locality.
