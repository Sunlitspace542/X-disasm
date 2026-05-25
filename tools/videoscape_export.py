#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


def clean_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def signed8(value: int) -> int:
    return value - 256 if value >= 0x80 else value


def parse_int(expr: str) -> int:
    expr = expr.strip()
    if not expr:
        raise ValueError("empty expression")

    substitutions = {
        "vLIST": "1",
        "vJUMP": "2",
        "vNONSPECIAL": "0x10",
        "vMIRRORED": "0x08",
        "fALWAYSVISIBLE": "0x80",
    }

    for key, replacement in substitutions.items():
        expr = re.sub(rf"\b{re.escape(key)}\b", replacement, expr)

    expr = expr.replace("$", "0x")

    return int(eval(expr, {"__builtins__": {}}, {}))


def parse_db_line(line: str):
    cleaned = clean_comment(line)
    if not cleaned.startswith("db "):
        raise ValueError(f"expected db line, got: {line}")
    body = cleaned[3:].strip()
    if not body:
        return []
    parts = [part.strip() for part in body.split(",")]
    return [parse_int(part) for part in parts]


def parse_dw_refs(line: str):
    cleaned = clean_comment(line)
    if not cleaned.startswith("dw "):
        raise ValueError(f"expected dw line, got: {line}")
    body = cleaned[3:].strip()
    refs = [part.strip() for part in body.split(",") if part.strip()]
    return refs


def parse_macro_args(line: str):
    cleaned = clean_comment(line)
    newline = cleaned
    if " " in newline:
        newline = newline.split(None, 1)[1].strip()
    parts = [part.strip() for part in newline.split(",") if part.strip()]
    return [parse_int(part) for part in parts]


def parse_verts_frame(frame_lines):
    points = []
    i = 0
    while i < len(frame_lines):
        line = clean_comment(frame_lines[i])
        if not line:
            i += 1
            continue
        if line == "db vEND":
            break

        # Every vertex group is encoded as: flag, count, count points.
        flag_values = parse_db_line(line)
        if len(flag_values) != 1:
            raise ValueError(f"expected single flag value in vertex group, got {flag_values!r} in {line!r}")

        count_values = parse_db_line(frame_lines[i + 1])
        if len(count_values) != 1:
            raise ValueError(f"expected single count value in vertex group, got {count_values!r}")

        count = count_values[0]
        mirrored = bool(flag_values[0] & 0x08)
        for j in range(count):
            coord_values = parse_db_line(frame_lines[i + 2 + j])
            if len(coord_values) != 3:
                raise ValueError(f"expected 3 coordinate values, got {coord_values!r}")
            x, y, z = (signed8(coord_values[0]), signed8(coord_values[1]), signed8(coord_values[2]))
            points.append((x, y, z))
            if mirrored:
                points.append((-x, y, z))

        i += 2 + count

    return points


def split_frame_blocks(lines):
    cleaned = [clean_comment(line) for line in lines]
    if not any(line.startswith(".frame") for line in cleaned if line):
        blocks = []
        current_block = []
        for line in cleaned:
            if not line:
                continue
            if line.endswith(":"):
                continue
            current_block.append(line)
            if line == "db vEND":
                blocks.append(([], current_block))
                current_block = []
        if current_block:
            blocks.append(([], current_block))
        return blocks

    blocks = []
    pending_labels = []
    current_block = []
    seen_data = False

    for line in cleaned:
        if not line:
            continue
        if line.startswith(".frame"):
            if current_block or seen_data:
                blocks.append((pending_labels.copy(), current_block))
                pending_labels = []
                current_block = []
                seen_data = False
            pending_labels.append(line.rstrip(":"))
            continue

        if pending_labels:
            seen_data = True
            current_block.append(line)
            continue

        if seen_data:
            current_block.append(line)

    if current_block or seen_data:
        blocks.append((pending_labels.copy(), current_block))

    return blocks


def parse_model_verts(verts_lines):
    # Prefer the vLIST frame order when present.
    for i, line in enumerate(verts_lines):
        cleaned = clean_comment(line)
        if cleaned == "db vLIST":
            count = parse_db_line(verts_lines[i + 1])[0]
            frame_refs = []
            for offset in range(count):
                frame_refs.append(parse_dw_refs(verts_lines[i + 2 + offset])[0])

            base_points = parse_verts_frame(verts_lines[:i])
            frame_blocks = split_frame_blocks(verts_lines[i + 2 + count :])
            frame_data = {}
            parsed_frames = []
            for labels, block in frame_blocks:
                parsed_points = parse_verts_frame(block)
                parsed_frames.append(parsed_points)
                for label in labels:
                    frame_data[label] = parsed_points

            if len(frame_refs) != count:
                raise ValueError("frame reference count mismatch")

            if all(ref in frame_data for ref in frame_refs):
                return [base_points + frame_data[ref] for ref in frame_refs]

            if len(parsed_frames) == len(frame_refs):
                return [base_points + parsed_frames[idx] for idx in range(len(frame_refs))]

            raise KeyError(frame_refs[0])

    return [parse_verts_frame(verts_lines)]


def parse_edges(edges_lines):
    edges = []
    for line in edges_lines:
        cleaned = clean_comment(line)
        if not cleaned:
            continue
        if cleaned.startswith("mEdge "):
            args = parse_macro_args(cleaned)
            if len(args) != 2:
                raise ValueError(f"expected 2 arguments in mEdge, got {args!r}")
            edges.append((args[0], args[1]))
        elif cleaned.startswith("db "):
            values = parse_db_line(cleaned)
            if len(values) == 2:
                edges.append((values[0], values[1]))
    return edges


def parse_faces(faces_lines):
    faces = []
    i = 0

    while i < len(faces_lines) and not clean_comment(faces_lines[i]):
        i += 1
    if i >= len(faces_lines):
        return faces

    face_count = parse_db_line(faces_lines[i])[0]
    i += 1

    for _ in range(face_count):
        while i < len(faces_lines) and not clean_comment(faces_lines[i]):
            i += 1
        if i >= len(faces_lines):
            raise ValueError("unexpected end of face data while reading normal")
        normal_values = parse_db_line(faces_lines[i])
        if len(normal_values) != 3:
            raise ValueError(f"expected 3 normal values, got {normal_values!r}")
        i += 1

        while i < len(faces_lines) and not clean_comment(faces_lines[i]):
            i += 1
        if i >= len(faces_lines):
            raise ValueError("missing edge count for face")
        edge_count = parse_db_line(faces_lines[i])[0] & 0x7F
        if edge_count == 0:
            raise ValueError("face edge count cannot be zero")
        i += 1

        while i < len(faces_lines) and not clean_comment(faces_lines[i]):
            i += 1
        if i >= len(faces_lines):
            raise ValueError("missing face payload for face")

        face_line = clean_comment(faces_lines[i])
        if face_line.startswith("fEdgeGroup "):
            face_indices = parse_macro_args(face_line)
            i += 1

            while i < len(faces_lines) and not clean_comment(faces_lines[i]):
                i += 1
            if i >= len(faces_lines):
                raise ValueError("missing fEdgeIdx for face")
            if not clean_comment(faces_lines[i]).startswith("fEdgeIdx "):
                raise ValueError(f"expected fEdgeIdx, got {faces_lines[i]!r}")
            parse_macro_args(clean_comment(faces_lines[i]))
            i += 1
        elif face_line.startswith("db "):
            face_payload = parse_db_line(face_line)
            if len(face_payload) == 4:
                i += 1
                while i < len(faces_lines) and not clean_comment(faces_lines[i]):
                    i += 1
                if i >= len(faces_lines):
                    raise ValueError("missing face index payload for raw face")
                if not clean_comment(faces_lines[i]).startswith("db "):
                    raise ValueError(f"expected raw face index payload, got {faces_lines[i]!r}")
                face_indices = parse_db_line(faces_lines[i])
                i += 1
            elif len(face_payload) >= 2:
                face_indices = face_payload
                i += 1
            else:
                raise ValueError(f"unsupported raw face payload: {face_payload!r}")
        else:
            raise ValueError(f"unsupported face payload: {face_line!r}")

        faces.append(face_indices)

    return faces


def extract_sections(model_lines):
    sections = {"verts": [], "edges": [], "faces": []}
    current = None
    for line in model_lines:
        cleaned = clean_comment(line)
        if not cleaned:
            continue
        if cleaned.startswith(".verts"):
            current = "verts"
            continue
        if cleaned.startswith(".edges"):
            current = "edges"
            continue
        if cleaned.startswith(".faces"):
            current = "faces"
            continue
        if current:
            sections[current].append(line)
    return sections


def find_models(source_text: str):
    models = []
    lines = source_text.splitlines()

    current_name = None
    current_lines = []
    for line in lines:
        cleaned = line.strip()
        label = cleaned.split(";", 1)[0].strip()
        if label.startswith("M_") and label.endswith(":"):
            if current_name is not None:
                models.append((current_name, current_lines))
            current_name = label[:-1]
            current_lines = []
            continue
        if current_name is not None:
            current_lines.append(line)

    if current_name is not None:
        models.append((current_name, current_lines))

    return models


def build_videoscape(
    lines,
    model_name,
    frames,
    edges,
    faces,
    animated,
    include_edges=True,
    include_faces=True,
):
    output = []
    if animated:
        output.append("3DAN")
        output.append(str(len(frames[0])))
        output.append(str(len(frames)))
        for frame in frames:
            for x, y, z in frame:
                output.append(f"{x} {y} {z}")
    else:
        output.append("3DG1")
        output.append(str(len(frames[0])))
        for x, y, z in frames[0]:
            output.append(f"{x} {y} {z}")

    all_faces = []
    if include_edges:
        for edge in edges:
            all_faces.append((10, [edge[0], edge[1]]))
    if include_faces:
        for face in faces:
            all_faces.append((20, face))

    for color, indices in all_faces:
        output.append(f"{len(indices)} {' '.join(str(idx) for idx in indices)} {color}")

    output.append("\x1a")
    return "\n".join(output)


def write_output(outdir: Path, model_name: str, content: str, animated: bool):
    outdir.mkdir(parents=True, exist_ok=True)
    extension = ".anm" if animated else ".txt"
    (outdir / f"{model_name}{extension}").write_text(content, encoding="utf-8")


def resolve_source_paths(source_path: Path | None) -> list[Path]:
    if source_path is not None:
        return [source_path]

    default_sources = [Path("src/bankb.asm"), Path("src/bank1.asm")]
    return [path for path in default_sources if path.exists()]


def convert_models(
    src_path: Path | None,
    outdir: Path,
    include_edges=True,
    include_faces=True,
):
    seen_models = set()
    for source_path in resolve_source_paths(src_path):
        source_text = source_path.read_text(encoding="utf-8")
        for model_name, model_lines in find_models(source_text):
            if model_name in seen_models:
                continue
            seen_models.add(model_name)

            sections = extract_sections(model_lines)
            frame_points = parse_model_verts(sections["verts"])
            edges = parse_edges(sections["edges"])
            faces = parse_faces(sections["faces"])

            animated = len(frame_points) > 1
            content = build_videoscape(
                [],
                model_name,
                frame_points,
                edges,
                faces,
                animated,
                include_edges=include_edges,
                include_faces=include_faces,
            )
            write_output(outdir, model_name, content, animated)


def main():
    parser = argparse.ArgumentParser(description="Convert X disassembly models to Videoscape text exports")
    parser.add_argument("source", nargs="?", help="Assembly source file to parse (defaults to bankb + bank1)")
    parser.add_argument("--outdir", default="videoscape", help="Directory for exported Videoscape text files")
    parser.add_argument("--no-edges", action="store_true", help="Exclude edge faces from the exported output")
    parser.add_argument("--no-faces", action="store_true", help="Exclude polygon faces from the exported output")
    args = parser.parse_args()

    source_path = Path(args.source) if args.source else None
    convert_models(
        source_path,
        Path(args.outdir),
        include_edges=not args.no_edges,
        include_faces=not args.no_faces,
    )


if __name__ == "__main__":
    main()
