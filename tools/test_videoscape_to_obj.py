import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from videoscape_to_obj import build_obj, write_animated_obj, write_obj


class VideoscapeToObjTests(unittest.TestCase):
    def test_build_obj_includes_vertices_and_face_records(self):
        points = [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
        edges = [(0, 1)]
        faces = [[0, 1, 2]]

        content = build_obj(points, edges, faces)

        self.assertIn("v 0 0 0", content)
        self.assertIn("v 1 0 0", content)
        self.assertIn("v 1 1 0", content)
        self.assertIn("f 1 2", content)
        self.assertIn("f 1 2 3", content)

    def test_write_obj_and_animated_outputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            outdir = Path(tmpdir)
            write_obj(outdir, "StaticModel", [(0, 0, 0)], [(0, 0)], [])
            write_animated_obj(
                outdir,
                "AnimatedModel",
                [[(0, 0, 0)], [(1, 1, 1)]],
                [(0, 0)],
                [],
            )

            self.assertTrue((outdir / "StaticModel.obj").exists())
            self.assertTrue((outdir / "AnimatedModel.anm" / "frame_000.obj").exists())
            self.assertTrue((outdir / "AnimatedModel.anm" / "frame_001.obj").exists())


if __name__ == "__main__":
    unittest.main()
