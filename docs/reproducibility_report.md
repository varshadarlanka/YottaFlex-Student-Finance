# Reproducibility Report

**Seed:** `20261022`  
**Mode compared:** `full`  
**Date verified:** 2026-11-01

## Method

Two independent full datasets were generated from empty SQLite databases in
separate Python processes with `PYTHONHASHSEED=random` and the same generation
seed. Each database was checked for row counts, SQLite integrity, and foreign
keys. Rows were sorted by their database ordering and hashed per table after
excluding runtime-generated timestamp fields: `created_at`, `updated_at`,
`performed_at`, `snapshot_date`, and `allocated_at`.

For each table, non-timestamp columns were read in schema order and rows in
`rowid` order. Each row was serialized as compact UTF-8 JSON with
`ensure_ascii=False`, followed by a newline, and streamed into the table's
SHA-256 digest.

## Results

Both generated databases had 15 tables and 562,051 rows. Both passed
`PRAGMA integrity_check` (`ok`) and had zero foreign-key violations. Each
table's non-timestamp content produced the same SHA-256 checksum in both runs.

| Table | Rows | Non-timestamp SHA-256 |
|---|---:|---|
| AuditEvents | 153,491 | `d19e46776c805e24cb8c2bbb35b287d34353bde3308ec88b6801c9c4cbe39341` |
| BalanceSnapshots | 1,474 | `ee034c8af0aee183de9c862c22ffb365411aa4a9c65470f2f79aa40cf3c45a59` |
| Eligibility | 15,000 | `caa5bcb55c678ca677127111a5a4e7ab48a0ed44c7cc51dcf4d02ff593132a01` |
| Enrollments | 27,770 | `823b08e901ae74c3a2d236cbff19fa006893883238d1c35493b48b11db24feb9` |
| FeeScheduleLines | 678 | `bdd7cb47fcbac4fbdf85103848cf0bc6a441313fbf152fe4fc25b28fe9af7886` |
| FeeSchedules | 120 | `27b0da45cef04910a874e55351fbef9d446f6ecfaeb3c1b124d493a96f542595` |
| InvoiceLines | 152,782 | `f1c277db9b66a62e1a2d4d1c87d6f2ca2d7e206fa5fdcd35cb95edc2d2ca628b` |
| Invoices | 30,000 | `6429df73b70a37c5360726415418d31c5a4900f4603fdeb3a22529964d57b60b` |
| PaymentAllocations | 119,735 | `1600a204e25f35aa3fd9c15bc71b713b5fdf61600a96964e50f9854a182e27a2` |
| Payments | 50,000 | `37377a9a5b9e6d6a1e6337332db0b54f070a5fde511688dd01cd1774bb230319` |
| Programs | 20 | `c70b0ef85dd1ec96f4793172902177dc767dbca7f7bc5fcd3d0e73cc96994e23` |
| Refunds | 970 | `818aa95e7355d306a382602932e218d0168bb86bc1ba2f33f898545c403cd09b` |
| Scholarships | 5 | `5fd737e33cfe3e80881797ce57298d31c6b039fc820f125b904a6d1f05362718` |
| Students | 10,000 | `39c34a4b05ad39e142223dc26f2bc71a37d3cb6a92bd230cacd5b50668406a07` |
| Terms | 6 | `1f578240d6b57f0fd313dc1e95dfadae7ec1f030476a950fa23923627f6e52c9` |
| **Total** | **562,051** | |

The required fresh full-mode volumes were met exactly: 10,000 students,
30,000 invoices, 15,000 eligibility awards, and 50,000 payments.

## Scope and limitation

The existing audited demo database was not overwritten. It has 505,231 rows
and includes preserved historical data and deliberate anomaly fixtures; its
counts are not expected to match a fresh full generation. The repeatability
check does not claim bit-for-bit SQLite file identity because database page
layout, metadata, and the excluded runtime timestamps can differ.
