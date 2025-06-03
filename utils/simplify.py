import json
import os
from shapely.geometry import shape, Polygon, MultiPolygon, mapping
from shapely.ops import unary_union

# --- Configuration ---
INPUT_FP = "data/NeiMongol/NeiMongol_4326.geojson"  # Path to your GADM JSON
OUTPUT_FP = "NeiMongol_simplified_360.geojson"
COORDS_OUTPUT_FP = "NeiMongol_simplified_360_coords.geojson"
QUERY_OUTPUT_FP = "NeiMongol_overpass_query.txt"
TARGET_VERTICES = 360
TOL_MIN, TOL_MAX = 0.0, 0.5  # Search range for simplification tolerance


'''This function should be linked with the output from the GADM API, instead of reading the file.'''
def prepare_geometry(input_shape, load_from_file=False, input_fp=None):
    if load_from_file:
        if input_fp is None:
            raise ValueError("input_fp must be provided when load_from_file is True")
        with open(input_fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
    else:
        data= input_shape

    geom = shape(data['features'][0]['geometry'])
    if isinstance(geom, MultiPolygon):
        merged = unary_union(geom)
        if isinstance(merged, Polygon):
            geom = merged
        else:
            geom = max(merged.geoms, key=lambda p: p.area)
    return geom



def find_tolerance_for_vertices(geom, target_vertices, tol_min=0.0, tol_max=0.5, iterations=10):
    def vertex_count(poly):
        return len(poly.exterior.coords)
    best_tol = tol_min
    best_count = vertex_count(geom)
    low, high = tol_min, tol_max
    for _ in range(iterations):
        mid = (low + high) / 2
        simp = geom.simplify(mid, preserve_topology=True)
        count = vertex_count(simp)
        if count <= target_vertices:
            best_tol, best_count = mid, count
            high = mid
        else:
            low = mid
    return best_tol, best_count


def simplify(geom, tol, output_path= None, export_json=False):
    if export_json and output_path is None:
        raise ValueError("output_path must be provided if export_json is True")
    simplified = geom.simplify(tol, preserve_topology=True)
    if export_json:
        feature = {
            "type": "Feature",
            "geometry": mapping(simplified),
            "properties": {}
        }
        fc = {"type": "FeatureCollection", "features": [feature]}
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(fc, f, ensure_ascii=False, indent=2)
    return simplified



def export_overpass_polygon(poly):
    polygon_coords = poly.exterior.coords
    poly_str = " ".join(f"{lat} {lon}" for lon, lat in polygon_coords)
    if not isinstance(poly_str, str):
        raise TypeError("Output must be of type string")
    return poly_str


def main():
    geom = prepare_geometry(input_shape, load_from_file=True, input_fp=INPUT_FP)
    tol, count = find_tolerance_for_vertices(geom, TARGET_VERTICES, TOL_MIN, TOL_MAX)
    simplified = simplify(geom, tol)
    export_overpass_polygon(simplified,)
    print(f"Wrote simplified geometry to {OUTPUT_FP}")
    print(f"Wrote simplified coordinates to {COORDS_OUTPUT_FP}")
    print(f"Wrote Overpass query to {QUERY_OUTPUT_FP}")
    print(f"Tolerance used: {tol:.6f}°, resulting vertices: {count}")

if __name__ == "__main__":
    main()
