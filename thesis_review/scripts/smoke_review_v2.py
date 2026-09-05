#!/usr/bin/env python3
"""Explicit, bounded one-actor CLI smoke on a synthetic two-page PDF (not a thesis review)."""
import argparse
from pathlib import Path
import tempfile
import time

import review_v2 as v


def synthetic_pdf(path):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    writer = PdfWriter()
    for lines in [
        ["A synthetic master's thesis", "1 Introduction", "Question: can sorting remove duplicates?",
         "2 Method", "Sort integer inputs, then discard adjacent equal elements.",
         "3 Results", "Input 3,1,3 yields 1,3. This only demonstrates one case.",
         "4 Conclusion", "The example illustrates the procedure, not population-wide performance."],
        ["References", "[1] Donald E. Knuth. The Art of Computer Programming.", "Volume 3: Sorting and Searching. Addison-Wesley. 1973."]]:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
        content = DecodedStreamObject()
        content.set_data(("BT /F1 12 Tf 45 735 Td 20 TL " + " ".join("(" + line.replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for line in lines) + " ET").encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, required=True)
    parser.add_argument("--pdftoppm", type=Path, required=True)
    args = parser.parse_args()
    # Keep diagnosis output for inspection; contains only synthetic material.
    root = Path(tempfile.mkdtemp(prefix="thesis-review-v2-smoke-"))
    source = root / "source"
    source.mkdir()
    synthetic_pdf(source / "sample.pdf")
    run_root = root / "run"
    v.init(argparse.Namespace(pdf=source / "sample.pdf", run=run_root, degree="master", policy=None,
                              codex=args.codex, pdftoppm=args.pdftoppm))
    state = v.load_state(run_root)
    state["limits"].update(actor_seconds=180, idle_seconds=90)
    auth = Path(v.os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    result = v.launch_actor(run_root, state, "R1", 1, time.monotonic()+180, auth if auth.is_file() else None)
    print(v.json.dumps({"synthetic_only": True, "root": str(root), **result}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
