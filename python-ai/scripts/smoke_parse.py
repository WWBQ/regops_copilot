from pathlib import Path
import sys

from app.config import ROOT_DIR
from app.ingest.parser import parse_pdf
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
DEFAULT_PDF = ROOT_DIR / "data" / "raw" / "002594_2024_annual.pdf"


def main() -> None:
    pdf = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else DEFAULT_PDF
    if not pdf.is_absolute():
        pdf = (Path.cwd() / pdf).resolve()
    blocks = parse_pdf(pdf)
    print(f"{pdf.name}: pages={len(blocks)}, tables={sum(len(b.tables) for b in blocks)}")
    for b in blocks:
        if b.tables:
            print(f"\n--- page {b.page_no} ---")
            print(b.text)
            for t in b.tables:
                print(t)

if __name__ == "__main__":
    main()