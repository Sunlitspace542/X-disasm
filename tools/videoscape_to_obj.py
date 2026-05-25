#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from videoscape_export import (
    extract_sections,
    find_models,
    parse_edges,
    parse_faces,
    parse_model_verts,
    resolve_source_paths,
)


def build_obj(points, edges, faces, include_edges=True, include_faces=True):
    lines = []
    for x, y, z in points:
        lines.append(f"v {x} {y} {z}")

    if include_edges:
        for edge in edges:
            lines.append(f"f {edge[0] + 1} {edge[1] + 1}")

    if include_faces:
        for face in faces:
            indices = " ".join(str(index + 1) for index in face)
            lines.append(f"f {indices}")

    return "\n".join(lines) + "\n"


def write_obj(outdir: Path, model_name: str, points, edges, faces, include_edges=True, include_faces=True):
    outdir.mkdir(parents=True, exist_ok=True)
    target = outdir / f"{model_name}.obj"
    target.write_text(
        build_obj(points, edges, faces, include_edges=include_edges, include_faces=include_faces),
        encoding="utf-8",
    )


def write_animated_obj(outdir: Path, model_name: str, frames, edges, faces, include_edges=True, include_faces=True):
    anim_dir = outdir / f"{model_name}.anm"
    anim_dir.mkdir(parents=True, exist_ok=True)
    for frame_index, frame in enumerate(frames):
        (anim_dir / f"frame_{frame_index:03d}.obj").write_text(
            build_obj(frame, edges, faces, include_edges=include_edges, include_faces=include_faces),
            encoding="utf-8",
        )


def convert_models_to_obj(
    src_path: Path | None,
    outdir: Path,
    include_edges=True,
    include_faces=True,
):
    seen_models = set()
    outdir.mkdir(parents=True, exist_ok=True)

    for source_path in resolve_source_paths(src_path):
        source_text = source_path.read_text(encoding="utf-8")
        for model_name, model_lines in find_models(source_text):
            if model_name in seen_models:
                continue
            seen_models.add(model_name)

            sections = extract_sections(model_lines)
            frames = parse_model_verts(sections["verts"])
            edges = parse_edges(sections["edges"])
            faces = parse_faces(sections["faces"])

            if len(frames) > 1:
                write_animated_obj(
                    outdir,
                    model_name,
                    frames,
                    edges,
                    faces,
                    include_edges=include_edges,
                    include_faces=include_faces,
                )
            else:
                write_obj(
                    outdir,
                    model_name,
                    frames[0],
                    edges,
                    faces,
                    include_edges=include_edges,
                    include_faces=include_faces,
                )


def main():
    parser = argparse.ArgumentParser(
        description="Convert X disassembly models to Wavefront OBJ exports"
    )
    parser.add_argument("source", nargs="?", help="Assembly source file to parse (defaults to bankb + bank1)")
    parser.add_argument(
        "--outdir",
        default="obj",
        help="Directory for exported OBJ files",
    )
    parser.add_argument("--no-edges", action="store_true", help="Exclude edge primitives from the exported OBJ")
    parser.add_argument("--no-faces", action="store_true", help="Exclude face primitives from the exported OBJ")
    args = parser.parse_args()

    source_path = Path(args.source) if args.source else None
    convert_models_to_obj(
        source_path,
        Path(args.outdir),
        include_edges=not args.no_edges,
        include_faces=not args.no_faces,
    )


if __name__ == "__main__":
    main()
