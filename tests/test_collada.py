from __future__ import annotations

import pytest

from beamng_mcp.errors import WorkspaceError
from beamng_mcp.services.collada import inspect_collada


def tiny_dae(*, meter: str = "1", matrix: str | None = None) -> bytes:
    transform = "" if matrix is None else f"<matrix>{matrix}</matrix>"
    return f"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
  <asset><unit meter="{meter}" name="meter"/><up_axis>Z_UP</up_axis></asset>
  <library_materials><material id="demo_mat" name="demo_mat"/></library_materials>
  <library_geometries>
    <geometry id="demo_mesh-mesh" name="demo_mesh"><mesh>
      <source id="demo_mesh-positions">
        <float_array id="demo_mesh-positions-array" count="12">
          -1 -2 0  1 -2 0  1 2 3  -1 2 3
        </float_array>
        <technique_common><accessor source="#demo_mesh-positions-array" count="4" stride="3">
          <param name="X" type="float"/><param name="Y" type="float"/>
          <param name="Z" type="float"/>
        </accessor></technique_common>
      </source>
      <vertices id="demo_mesh-vertices">
        <input semantic="POSITION" source="#demo_mesh-positions"/>
      </vertices>
      <triangles count="2" material="demo_mat"><input semantic="VERTEX"
        source="#demo_mesh-vertices" offset="0"/><p>0 1 2 0 2 3</p></triangles>
    </mesh></geometry>
  </library_geometries>
  <library_visual_scenes><visual_scene id="Scene" name="Scene">
    <node id="demo_mesh" name="demo_mesh">{transform}
      <instance_geometry url="#demo_mesh-mesh"/>
    </node>
  </visual_scene></library_visual_scenes>
  <scene><instance_visual_scene url="#Scene"/></scene>
</COLLADA>
""".encode()


def test_collada_inspection_verifies_axis_identity_names_and_bounds() -> None:
    identity = "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"
    result = inspect_collada(
        tiny_dae(matrix=identity),
        expected_mesh_name="demo_mesh",
        expected_material_name="demo_mat",
    )
    assert result.bounds_min == (-1.0, -2.0, 0.0)
    assert result.bounds_max == (1.0, 2.0, 3.0)
    assert result.vertex_count == 4


def test_collada_inspection_rejects_units_transform_and_external_references() -> None:
    with pytest.raises(WorkspaceError, match=r"meter must be 1\.0"):
        inspect_collada(
            tiny_dae(meter="0.01"),
            expected_mesh_name="demo_mesh",
            expected_material_name="demo_mat",
        )

    translated = "1 0 0 4 0 1 0 0 0 0 1 0 0 0 0 1"
    with pytest.raises(WorkspaceError, match="identity matrix"):
        inspect_collada(
            tiny_dae(matrix=translated),
            expected_mesh_name="demo_mesh",
            expected_material_name="demo_mat",
        )

    malicious = tiny_dae().replace(b"</COLLADA>", b'<extra url="file:///secret"/></COLLADA>')
    with pytest.raises(WorkspaceError, match="external URL"):
        inspect_collada(
            malicious,
            expected_mesh_name="demo_mesh",
            expected_material_name="demo_mat",
        )


def test_collada_inspection_rejects_xml_entities() -> None:
    payload = tiny_dae().replace(
        b"<COLLADA ", b'<!DOCTYPE x [<!ENTITY leak SYSTEM "file:///secret">]><COLLADA '
    )
    with pytest.raises(WorkspaceError, match="DOCTYPE"):
        inspect_collada(
            payload,
            expected_mesh_name="demo_mesh",
            expected_material_name="demo_mat",
        )


def test_collada_inspection_rejects_unstaged_relative_textures() -> None:
    payload = tiny_dae().replace(
        b"<library_materials>",
        b'<library_images><image id="paint"><init_from>paint.color.png</init_from>'
        b"</image></library_images><library_materials>",
    )
    with pytest.raises(WorkspaceError, match="external image textures"):
        inspect_collada(
            payload,
            expected_mesh_name="demo_mesh",
            expected_material_name="demo_mat",
        )


def test_collada_uses_only_referenced_positions_from_the_exact_instanced_geometry() -> None:
    payload = (
        tiny_dae()
        .replace(
            b'count="12">\n          -1 -2 0  1 -2 0  1 2 3  -1 2 3',
            b'count="15">\n          -1 -2 0  1 -2 0  1 2 3  -1 2 3  99 99 99',
        )
        .replace(
            b'count="4" stride="3"',
            b'count="5" stride="3"',
        )
        .replace(
            b"  </library_geometries>",
            b"""    <geometry id="decoy-geometry" name="demo_mesh"><mesh>
      <source id="decoy-positions"><float_array id="decoy-array" count="9">
        -500 -500 -500  500 500 500  0 0 0
      </float_array><technique_common><accessor source="#decoy-array" count="3" stride="3"/>
      </technique_common></source>
      <vertices id="decoy-vertices"><input semantic="POSITION" source="#decoy-positions"/>
      </vertices><triangles count="1" material="demo_mat"><input semantic="VERTEX"
        source="#decoy-vertices" offset="0"/><p>0 1 2</p></triangles>
    </mesh></geometry>
  </library_geometries>""",
        )
        .replace(
            b"    </node>",
            b"""    </node>
    <node id="decoy" name="decoy"><instance_geometry url="#decoy-geometry"/></node>""",
        )
    )

    result = inspect_collada(
        payload,
        expected_mesh_name="demo_mesh",
        expected_material_name="demo_mat",
    )

    assert result.bounds_min == (-1.0, -2.0, 0.0)
    assert result.bounds_max == (1.0, 2.0, 3.0)
    assert result.vertex_count == 4
    assert (99.0, 99.0, 99.0) not in result.positions


@pytest.mark.parametrize(
    "transform",
    (
        "<lookat>0 0 1 0 0 0 0 1 0</lookat>",
        "<skew>45 1 0 0 0 1 0</skew>",
    ),
)
def test_collada_rejects_non_matrix_scene_transforms(transform: str) -> None:
    payload = tiny_dae().replace(
        b'<instance_geometry url="#demo_mesh-mesh"/>',
        transform.encode() + b'<instance_geometry url="#demo_mesh-mesh"/>',
    )

    with pytest.raises(WorkspaceError, match="baked identity transform"):
        inspect_collada(
            payload,
            expected_mesh_name="demo_mesh",
            expected_material_name="demo_mat",
        )


def test_collada_resolves_the_material_bound_to_the_surface_primitive() -> None:
    payload = (
        tiny_dae()
        .replace(
            b'<material id="demo_mat" name="demo_mat"/>',
            b'<material id="material-id" name="demo_actual_mat"/>',
        )
        .replace(
            b'material="demo_mat"',
            b'material="surface_slot"',
        )
        .replace(
            b'<instance_geometry url="#demo_mesh-mesh"/>',
            b"""<instance_geometry url="#demo_mesh-mesh"><bind_material><technique_common>
        <instance_material symbol="surface_slot" target="#material-id"/>
      </technique_common></bind_material></instance_geometry>""",
        )
    )

    result = inspect_collada(
        payload,
        expected_mesh_name="demo_mesh",
        expected_material_name="demo_actual_mat",
    )
    assert result.material_names == ("demo_actual_mat",)

    with pytest.raises(WorkspaceError, match="expected material"):
        inspect_collada(
            payload,
            expected_mesh_name="demo_mesh",
            expected_material_name="surface_slot",
        )
