{% snapshot my_snapshot %}
    {{
        config(
            target_database="target_database",
            target_schema="target_schema",
            unique_key='id',
            strategy='timestamp',
            updated_at='updated_at',
        )
    }}
    select * from {{database}}.{{schema}}.seed
{% endsnapshot %}
