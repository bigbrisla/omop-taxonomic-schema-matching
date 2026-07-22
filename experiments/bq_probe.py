from google.cloud import bigquery
client = bigquery.Client()
sql = """
SELECT table_name
FROM `bigquery-public-data.cms_synthetic_patient_data_omop.INFORMATION_SCHEMA.TABLES`
WHERE table_name IN ('concept','concept_ancestor','concept_relationship',
                     'condition_occurrence','procedure_occurrence','observation','person')
ORDER BY table_name
"""
for r in client.query(sql).result():
    print(" -", r.table_name)
