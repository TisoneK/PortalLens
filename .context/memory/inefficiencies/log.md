
---
## 2026-08-02 — Buffy / deepseek-v4-flash (Session 17)
- **Problem:** The first ADR-20 edit accidentally overwrote `.context/memory/plans/decisions.md` instead of appending, and one subagent attempted to use an unavailable reporting tool. The first Wi-Fi test pass also exposed a bad fake-adapter assertion and a real serialization privacy gap.
- **Cost:** ~10 min of repair/review effort; no product data was lost because the ADR file was restored from `HEAD` before appending, and the privacy issue was fixed before commit.
- **Cause:** The initial context edit used a full-file write for an append-only file; the fake adapter returned an empty tuple while the test asserted truthiness; allow-listed fields alone did not sanitize sensitive URL values or raw adapter errors.
- **Workaround / fix:** Restored the ADR file from `HEAD` and appended ADR-20 with a shell append; corrected the fixture; added URL query/path/fragment redaction and replaced persisted error text with a generic marker; reran reviewer and all gates.
- **Prevent next time:** Never use whole-file replacement for append-only context files—restore from `HEAD` and append if an accidental overwrite occurs. Treat serializer allow-lists as necessary but not sufficient when values can contain URLs or command output. Verify subagent tool availability through the current tool list before relying on its report channel.
