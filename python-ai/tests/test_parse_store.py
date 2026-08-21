from app.ingest.models import PageBlock, TableBlock, TableCellBlock
from app.ingest.parse_store import ParseArtifactStore
from app.storage.local import LocalObjectStore


def _sample_blocks() -> list[PageBlock]:
    cell = TableCellBlock(text="100", row=0, col=1, bbox=(1.0, 2.0, 3.0, 4.0))
    table = TableBlock(page_no=1, rows=[["a", "100"]], cells=[cell], markdown="| a | 100 |")
    return [
        PageBlock(
            page_no=1,
            text="示例正文",
            tables=[table],
            source_file="demo.pdf",
            content_hash="sha256:demo",
        )
    ]


def test_parse_artifact_store_save_load(tmp_path):
    store = LocalObjectStore(
        tmp_path / "objects",
        default_bucket="regops-docs",
        public_base_url="http://test",
        presign_secret="secret",
    )
    artifact_store = ParseArtifactStore(store, default_bucket="regops-docs")
    blocks = _sample_blocks()
    key, content_hash = artifact_store.save_blocks("demo_doc", blocks)
    assert key.endswith(".parse.json")
    assert content_hash == "sha256:demo"
    assert artifact_store.exists("demo_doc", content_hash)
    loaded = artifact_store.load_blocks("demo_doc", content_hash)
    assert loaded[0].text == blocks[0].text
