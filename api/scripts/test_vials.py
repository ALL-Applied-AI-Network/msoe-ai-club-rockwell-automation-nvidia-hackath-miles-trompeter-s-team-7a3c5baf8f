import unittest

from vials import vial_box


class VialLabelsTest(unittest.TestCase):
    def test_liquid_is_removed_not_renamed(self):
        self.assertIsNone(vial_box("1 0.5 0.5 0.2 0.4", 0))

    def test_box_is_preserved_and_class_remapped(self):
        row = vial_box("3 0.5 0.4 0.2 0.6", 3).split()
        self.assertEqual(row[0], "0")
        self.assertEqual(list(map(float, row[1:])), [0.5, 0.4, 0.2, 0.6])

    def test_polygon_becomes_enclosing_rectangle(self):
        row = vial_box("0 0.1 0.2 0.5 0.2 0.4 0.8", 0).split()
        self.assertEqual(list(map(float, row[1:])), [0.3, 0.5, 0.4, 0.6])

    def test_invalid_vial_labels_fail(self):
        for row in ("0 nan 0.5 0.2 0.3", "0 0.5 0.5 0 0.3",
                    "0 1.2 0.5 0.2 0.3", "0 0.1 0.2 0.3"):
            with self.subTest(row=row), self.assertRaises(ValueError):
                vial_box(row, 0)


if __name__ == "__main__":
    unittest.main()
