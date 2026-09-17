import osmium
import shapely.wkb

INCLUDED_HIGHWAYS = {
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified",
    "residential"
}

class RoadHandler(osmium.SimpleHandler):
    def __init__(self):
        super(RoadHandler, self).__init__()
        self.roads = []
        self.wkbfab = osmium.geom.WKBFactory()

    def way(self, w):
        if 'highway' in w.tags and w.tags['highway'] in INCLUDED_HIGHWAYS:
            try:
                wkb = self.wkbfab.create_linestring(w)
                geom = shapely.wkb.loads(wkb, hex=True)
                self.roads.append({
                    'osm_id': w.id,
                    'highway': w.tags['highway'],
                    'geometry': geom
                })
            except Exception as e:
                pass

handler = RoadHandler()
handler.apply_file('.osm_cache/north-eastern-zone-latest.osm.pbf', locations=True)
print(f"Extracted {len(handler.roads)} roads.")
