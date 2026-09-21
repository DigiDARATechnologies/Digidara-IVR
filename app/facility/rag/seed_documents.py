"""Reviewed sample Facility Operations knowledge used by the Nectar demo."""

FACILITY_SEED_DOCUMENTS = (
    {
        "id": "hvac_low_airflow_v1",
        "title": "AHU low-airflow troubleshooting procedure",
        "text": (
            "For an AHU reporting low airflow, verify the differential pressure across filters, "
            "inspect supply and return dampers for their commanded position, confirm fan status and VFD speed, "
            "and inspect belts and fan rotation. Escalate for maintenance when measured airflow remains below 80 "
            "percent of design after safe operator checks. Do not bypass safety interlocks."
        ),
        "metadata": {"document_type": "troubleshooting", "revision": "1.0"},
    },
    {
        "id": "chiller_energy_v1",
        "title": "Chiller elevated-energy investigation guide",
        "text": (
            "When chiller power exceeds its normal baseline, compare leaving-water temperature, condenser-water "
            "temperature, load percentage, and active alarms. Elevated energy alone is not proof of a fault. "
            "Investigate related air-handling units and airflow restrictions before creating corrective maintenance."
        ),
        "metadata": {"document_type": "operating_procedure", "revision": "1.0"},
    },
    {
        "id": "hvac_safety_v1",
        "title": "HVAC operational safety policy",
        "text": (
            "Only authorized technicians may isolate electrical equipment, override controls, or enter restricted "
            "plant rooms. The assistant may create a service request after an operator confirms it, but must never "
            "instruct an operator to defeat interlocks, change setpoints, or perform electrical work."
        ),
        "metadata": {"document_type": "safety_policy", "revision": "1.0"},
    },
)
