from sqlalchemy.types import TypeDecorator, String
from geoalchemy2 import Geometry

class FlexibleGeometry(TypeDecorator):
    """
    A SQLAlchemy type that uses PostGIS Geometry when connecting to PostgreSQL,
    and falls back to a simple String (storing WKT or GeoJSON) for SQLite.
    This preserves SQLite testability while using true spatial operations in production.
    """
    impl = String
    cache_ok = True
    spatial_index = False

    def __init__(self, geometry_type="GEOMETRY", srid=4326, **kwargs):
        super().__init__(**kwargs)
        self.geometry_type = geometry_type
        self.srid = srid

    def load_dialect_impl(self, dialect=None):
        if dialect and dialect.name == "postgresql":
            return dialect.type_descriptor(Geometry(geometry_type=self.geometry_type, srid=self.srid))
        elif dialect:
            return dialect.type_descriptor(String())
        else:
            return String()

    def bind_expression(self, bindvalue):
        """Allows passing WKT strings; GeoAlchemy handles the conversion to PostGIS binary."""
        return bindvalue

    def column_expression(self, col):
        """Extract geometry as WKT or GeoJSON depending on the dialect?"""
        # We handle this manually in queries when needed (ST_AsGeoJSON) 
        # so for the raw column we just return it.
        return col
