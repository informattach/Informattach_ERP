from database import db
with open('fix_uuid_defaults.sql', 'r') as file:
    sql = file.read()
response = db.run_sql_query(sql)
print("Execute result:", response)
