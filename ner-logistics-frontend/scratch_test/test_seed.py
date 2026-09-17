import unittest
from seed_demo_data import parse_wkt_linestring, select_connected_subgraph

class TestSeedDemoData(unittest.TestCase):

    def test_parse_wkt_linestring(self):
        wkt = "LINESTRING (91.7 26.1, 91.8 26.2)"
        res = parse_wkt_linestring(wkt)
        self.assertEqual(res["start_lon"], 91.7)
        self.assertEqual(res["start_lat"], 26.1)
        self.assertEqual(res["end_lon"], 91.8)
        self.assertEqual(res["end_lat"], 26.2)

    def test_parse_wkt_malformed(self):
        wkt = "INVALID STRING"
        with self.assertRaises(Exception):
            parse_wkt_linestring(wkt)

    def test_select_connected_subgraph(self):
        edges = [
            {"u": 1, "v": 2, "geometry": "LINESTRING(1 1, 2 2)"},
            {"u": 2, "v": 3, "geometry": "LINESTRING(2 2, 3 3)"},
            {"u": 3, "v": 4, "geometry": "LINESTRING(3 3, 4 4)"},
            {"u": 5, "v": 6, "geometry": "LINESTRING(5 5, 6 6)"}, # disconnected
        ]
        subgraph = select_connected_subgraph(edges, target_size=2)
        # Should pick from the largest component (1,2,3,4) which has 3 edges
        self.assertEqual(len(subgraph), 2)
        # Verify it does not include the disconnected edge 5->6
        for edge in subgraph:
            self.assertTrue(edge["u"] in [1,2,3,4] and edge["v"] in [1,2,3,4])

if __name__ == '__main__':
    unittest.main()
