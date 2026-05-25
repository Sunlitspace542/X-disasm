import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from videoscape_export import (
    build_videoscape,
    parse_edges,
    parse_faces,
    parse_model_verts,
    parse_verts_frame,
    signed8,
    write_output,
)


class VideoscapeExportTests(unittest.TestCase):
    def test_signed8(self):
        self.assertEqual(signed8(0xF6), -10)
        self.assertEqual(signed8(0x10), 16)

    def test_parse_verts_frame(self):
        frame_lines = [
            "db vNONSPECIAL",
            "db 2",
            "db $00, $00, $00",
            "db $10, $00, $00",
            "db vEND",
        ]
        points = parse_verts_frame(frame_lines)
        self.assertEqual(points, [(0, 0, 0), (16, 0, 0)])

    def test_parse_model_verts_non_animated(self):
        section = [
            "db vNONSPECIAL",
            "db 1",
            "db $00, $00, $00",
            "db vEND",
        ]
        frames = parse_model_verts(section)
        self.assertEqual(frames, [[(0, 0, 0)]])

    def test_parse_model_verts_animated_alias_frames(self):
        section = [
            "db vLIST",
            "db 2",
            "dw .frame0",
            "dw .frame15",
            ".frame0",
            ".frame15",
            "db vNONSPECIAL",
            "db 1",
            "db $00, $00, $00",
            "db vEND",
        ]
        frames = parse_model_verts(section)
        self.assertEqual(frames, [[(0, 0, 0)], [(0, 0, 0)]])

    def test_parse_model_verts_includes_static_vertices_before_vlist(self):
        section = [
            "db vNONSPECIAL",
            "db 1",
            "db $10, $00, $00",
            "db vNONSPECIAL | vMIRRORED",
            "db 1",
            "db $20, $00, $00",
            "db vLIST",
            "db 1",
            "dw .frame0",
            ".frame0",
            "db vNONSPECIAL",
            "db 1",
            "db $00, $10, $00",
            "db vEND",
        ]
        frames = parse_model_verts(section)
        self.assertEqual(frames, [[(16, 0, 0), (32, 0, 0), (-32, 0, 0), (0, 16, 0)]])

    def test_parse_edges_and_faces(self):
        edge_lines = [
            "mEdge 0, 1",
        ]
        face_lines = [
            "db 1",
            "db $00, $00, $00",
            "db 3 | fALWAYSVISIBLE",
            "fEdgeGroup $0, $1, $2",
            "fEdgeIdx $0, $1, $2",
        ]

        edges = parse_edges(edge_lines)
        faces = parse_faces(face_lines)

        self.assertEqual(edges, [(0, 1)])
        self.assertEqual(faces, [[0, 1, 2]])

    def test_build_videoscape_output(self):
        frame_points = [[(0, 0, 0), (1, 2, 3)]]
        content = build_videoscape([], "TestModel", frame_points, [(0, 1)], [[0, 1]], False)

        self.assertIn("3DG1", content)
        self.assertIn("10", content)
        self.assertIn("20", content)
        self.assertIn("2 0 1 10", content)
        self.assertIn("2 0 1 20", content)

    def test_write_output_uses_expected_extension_by_animation_type(self):
        outdir = Path(__file__).resolve().parent / "_tmp_videoscape_test"
        try:
            write_output(outdir, "StaticModel", "3DG1", False)
            write_output(outdir, "AnimatedModel", "3DAN", True)

            self.assertTrue((outdir / "StaticModel.txt").exists())
            self.assertTrue((outdir / "AnimatedModel.anm").exists())
            self.assertFalse((outdir / "AnimatedModel.txt").exists())
        finally:
            for path in sorted(outdir.iterdir(), reverse=True):
                if path.is_file() or path.is_symlink():
                    path.unlink()
                else:
                    path.rmdir()
            if outdir.exists():
                outdir.rmdir()


if __name__ == "__main__":
    unittest.main()
