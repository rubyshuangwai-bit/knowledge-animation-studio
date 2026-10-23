"""Remove only numbered render chunks after validating their chapter output."""
from pathlib import Path
import re
import subprocess

def cleanup_render_chunks(root, chapter_id):
    root = Path(root).resolve()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", chapter_id):
        raise ValueError("Unsafe chapter id")
    chunks = root / "tmp" / "render_chunks" / chapter_id
    if not chunks.exists():
        return 0
    if any(p.is_symlink() for p in (root / "tmp", chunks.parent, chunks)):
        raise ValueError("Symlink chunk directory refused")
    video = root / "chapters" / chapter_id / (chapter_id + ".mp4")
    if not video.is_file() or video.stat().st_size == 0:
        raise ValueError("Missing chapter video; chunks preserved")
    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(video),
                    "-f", "null", "-"], check=True, capture_output=True)
    removed = 0
    for path in chunks.iterdir():
        if re.fullmatch(r"[0-9]+\.mp4", path.name) and path.is_file() and not path.is_symlink():
            removed += path.stat().st_size
            path.unlink()
    return removed
