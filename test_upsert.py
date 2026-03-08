from database import db

payload = {
    "marketplace": "ebay",
    "category_id": "test_id",
    "category_name": "Test Cat"
}

try:
    print("Normal insert...")
    # This should fail if it exists, but will prove column 'marketplace' is in the cache.
    db.client.table('marketplace_categories').insert(payload).execute()
    print("Insert success.")
except Exception as e:
    print("Insert error:", e)

try:
    print("Upsert missing ID without conflict...")
    db.client.table('marketplace_categories').upsert(payload, ignore_duplicates=True).execute()
    print("Upsert success.")
except Exception as e:
    print("Upsert error:", e)

try:
    print("Upsert with composite conflict string...")
    db.client.table('marketplace_categories').upsert(payload, on_conflict='marketplace,category_id').execute()
    print("Upsert composite success.")
except Exception as e:
    print("Upsert composite error:", e)
