# Slice T3b: admin material asset commit

Branch: `feature/claude-financial-core` · ERR block: 470.

`POST /api/v1/materials/<uuid>/assets/commit/` (admin only, `upload` throttle), body `{kind: 'pdf'|'audio', key, etag?}`.

- The admin presigns into `incoming/<admin id>/` (the existing presign endpoint already lets admins write anywhere); the commit refuses any other key (also `..`).
- Checks before anything is copied: ETag equals the one the admin saw (and the ranged read is `If-Match` the stored ETag), the declared content type matches the kind, size within 25 MB, magic bytes match the declared type (`%PDF-`; MP3 `ID3` or frame sync; `OggS`; `RIFF....WAVE`).
- The object is copied to `materials/<material id>/<kind>-<random>.<ext>` in the public bucket and set on `Material.pdf_file` / `audio_snippet_file`; the quarantine copy and the replaced object are deleted on commit (`transaction.on_commit`), and a failed database write removes the copy.
- Errors: rejected upload 400, storage outage 503. `audio/ogg` was added to the upload allowlist.

`tests/test_materials_asset_commit.py` (20). Not done: idempotent re-commit of the same ETag (a retry after success gets 400 "not found" because the quarantine object is gone).
