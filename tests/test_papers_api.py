"""Milestone 0/1 API smoke tests."""

from __future__ import annotations

from pathlib import Path


def _minimal_pdf() -> bytes:
    return b"""%PDF-1.1
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] >>endobj
xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer<< /Size 4 /Root 1 0 R >>
startxref
190
%%EOF
"""


def _text_pdf(tmp_path: Path) -> Path:
    import fitz

    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=400, height=500)
    page.insert_text((72, 72), "Hello PaperLens Parsing.", fontsize=14)
    page.insert_text((72, 120), "This is a second sentence for structure. DOI: 10.1234/paperlens", fontsize=11)
    doc.set_metadata(
        {
            "title": "PaperLens Metadata Test",
            "author": "Ada Lovelace; Alan Turing",
            "subject": "A metadata extraction API test.",
            "keywords": "layout, parsing",
        }
    )
    doc.save(path.as_posix())
    doc.close()
    return path


def test_health(client):
    c, _ = client
    res = c.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_upload_list_rename_delete(client):
    c, _ = client
    pdf = _minimal_pdf()
    res = c.post(
        "/api/papers",
        files={"file": ("demo.pdf", pdf, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    paper = res.json()
    assert paper["filename"] == "demo.pdf"
    assert paper["status"] == "queued"
    paper_id = paper["id"]

    dup = c.post(
        "/api/papers",
        files={"file": ("demo2.pdf", pdf, "application/pdf")},
    )
    assert dup.status_code == 201
    assert dup.json()["id"] == paper_id

    listed = c.get("/api/papers")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    renamed = c.patch(f"/api/papers/{paper_id}", json={"title": "演示论文"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "演示论文"

    file_res = c.get(f"/api/papers/{paper_id}/file")
    assert file_res.status_code == 200
    assert file_res.headers["content-type"].startswith("application/pdf")

    deleted = c.delete(f"/api/papers/{paper_id}")
    assert deleted.status_code == 204
    assert c.get("/api/papers").json()["total"] == 0


def test_hierarchical_folders_and_single_folder_move(client):
    c, _ = client
    root = c.post("/api/folders", json={"name": "研究方向", "parent_id": None})
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]
    child = c.post("/api/folders", json={"name": "线性注意力", "parent_id": root_id})
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    duplicate = c.post("/api/folders", json={"name": "研究方向", "parent_id": None})
    assert duplicate.status_code == 409
    cycle = c.patch(f"/api/folders/{root_id}", json={"parent_id": child_id})
    assert cycle.status_code == 409

    uploaded = c.post(
        "/api/papers",
        data={"folder_id": root_id},
        files={"file": ("folder-demo.pdf", _minimal_pdf(), "application/pdf")},
    )
    assert uploaded.status_code == 201, uploaded.text
    paper_id = uploaded.json()["id"]
    assert uploaded.json()["folder_id"] == root_id

    moved = c.patch(f"/api/papers/{paper_id}", json={"folder_id": child_id})
    assert moved.status_code == 200
    assert moved.json()["folder_id"] == child_id
    assert c.get("/api/papers", params={"folder_id": root_id}).json()["total"] == 0
    assert c.get("/api/papers", params={"folder_id": child_id}).json()["total"] == 1

    deleted_root = c.delete(f"/api/folders/{root_id}")
    assert deleted_root.status_code == 204
    folder_rows = c.get("/api/folders").json()["items"]
    assert folder_rows[0]["id"] == child_id
    assert folder_rows[0]["parent_id"] is None
    assert c.get(f"/api/papers/{paper_id}").json()["folder_id"] == child_id

    assert c.delete(f"/api/folders/{child_id}").status_code == 204
    assert c.get("/api/papers", params={"view": "unfiled"}).json()["total"] == 1


def test_paper_trash_restore_and_permanent_delete(client):
    c, _ = client
    uploaded = c.post(
        "/api/papers",
        files={"file": ("trash-demo.pdf", _minimal_pdf(), "application/pdf")},
    )
    paper_id = uploaded.json()["id"]

    assert c.delete(f"/api/papers/{paper_id}").status_code == 204
    assert c.get("/api/papers").json()["total"] == 0
    assert c.get("/api/papers", params={"view": "trash"}).json()["total"] == 1
    assert c.get(f"/api/papers/{paper_id}").status_code == 404

    restored = c.post(f"/api/papers/{paper_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None

    assert c.delete(f"/api/papers/{paper_id}").status_code == 204
    assert c.delete(f"/api/papers/{paper_id}/permanent").status_code == 204
    assert c.get("/api/papers", params={"view": "trash"}).json()["total"] == 0


def test_reject_non_pdf(client):
    c, _ = client
    res = c.post(
        "/api/papers",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400


def test_parse_document(client, tmp_path: Path):
    from app.workers.parse_worker import _process_one

    c, _ = client
    path = _text_pdf(tmp_path)
    with path.open("rb") as f:
        res = c.post(
            "/api/papers",
            files={"file": ("sample.pdf", f.read(), "application/pdf")},
        )
    assert res.status_code == 201, res.text
    paper_id = res.json()["id"]
    assert res.json()["title"] == "PaperLens Metadata Test"
    assert res.json()["authors"] == ["Ada Lovelace", "Alan Turing"]
    assert res.json()["doi"] == "10.1234/paperlens"
    assert res.json()["metadata_source"] == "pdf"

    refreshed = c.post(f"/api/papers/{paper_id}/metadata")
    assert refreshed.status_code == 200
    assert refreshed.json()["authors"] == ["Ada Lovelace", "Alan Turing"]

    assert _process_one() is True
    meta = c.get(f"/api/papers/{paper_id}").json()
    assert meta["status"] == "ready", meta.get("error_message")

    doc = c.get(f"/api/papers/{paper_id}/document")
    assert doc.status_code == 200
    body = doc.json()
    assert body["page_count"] >= 1
    assert body["blocks"]
    assert any("Hello PaperLens" in (b.get("source_text") or "") for b in body["blocks"])

    retry = c.post(f"/api/papers/{paper_id}/parse")
    assert retry.status_code == 202
    assert _process_one() is True
    assert c.get(f"/api/papers/{paper_id}").json()["status"] == "ready"
