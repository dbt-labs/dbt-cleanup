from dbt_autofix.fields_properties_configs import fields_per_node_type


def test_fields_no_overlap():
    for node_type in fields_per_node_type:
        intersection = fields_per_node_type[node_type].allowed_config_fields.intersection(
            fields_per_node_type[node_type].allowed_properties
        )
        assert len(intersection) == 0, (
            f"Fields {intersection} are in both allowed_config_fields and allowed_properties for {node_type}"
        )


def test_meta_as_config_field():
    for node_type in fields_per_node_type:
        assert "meta" in fields_per_node_type[node_type].allowed_config_fields, (
            f"meta is in allowed_config_fields for {node_type}"
        )
        assert "meta" not in fields_per_node_type[node_type].allowed_properties, (
            f"meta is in allowed_properties for {node_type}"
        )
