import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# We default to local MongoDB
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DB_NAME = "taskworkflow"

mongo_client = None
mongo_db = None

try:
    print(f"MongoDB: Attempting to connect to MongoDB URI: {MONGODB_URI}")
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
    # Ping database to force connection check
    mongo_client.admin.command('ping')
    mongo_db = mongo_client[DB_NAME]
    print("MongoDB: Successfully connected to MongoDB server.")
except Exception as e:
    print(f"MongoDB: Server connection failed ({e}). Enabling in-memory fallback collections.")
    mongo_db = None

class InMemoryCollection:
    def __init__(self, name):
        self.name = name
        self.data = []
        self._next_id = 1

    def insert_one(self, doc):
        if "_id" not in doc:
            doc["_id"] = str(self._next_id)
            self._next_id += 1
        # Make a copy to avoid external mutability issues
        doc_copy = doc.copy()
        self.data.append(doc_copy)
        return doc_copy

    def find(self, query=None, projection=None):
        if not query:
            return self.data
        
        results = []
        for doc in self.data:
            match = True
            for k, v in query.items():
                if isinstance(v, dict):
                    # Basic support for search operators if any
                    pass
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                results.append(doc.copy())
        return results

    def find_one(self, query):
        res = self.find(query)
        return res[0] if res else None

    def delete_many(self, query):
        initial_len = len(self.data)
        self.data = [
            doc for doc in self.data 
            if not all(doc.get(k) == v for k, v in query.items())
        ]
        deleted_count = initial_len - len(self.data)
        
        class DeleteResult:
            def __init__(self, count):
                self.deleted_count = count
        return DeleteResult(deleted_count)

    def delete_one(self, query):
        for idx, doc in enumerate(self.data):
            if all(doc.get(k) == v for k, v in query.items()):
                self.data.pop(idx)
                break
        
        class DeleteResult:
            def __init__(self, count):
                self.deleted_count = count
        return DeleteResult(1)

    def update_one(self, query, update, upsert=False):
        docs = self.find(query)
        if docs:
            # find original in self.data
            for doc in self.data:
                if all(doc.get(k) == v for k, v in query.items()):
                    if "$set" in update:
                        doc.update(update["$set"])
                    break
        elif upsert:
            new_doc = query.copy()
            if "$set" in update:
                new_doc.update(update["$set"])
            self.insert_one(new_doc)
            
        class UpdateResult:
            def __init__(self, matched, modified):
                self.matched_count = matched
                self.modified_count = modified
        return UpdateResult(1, 1)

class InMemoryMongoMock:
    def __init__(self):
        self._collections = {}

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = InMemoryCollection(name)
        return self._collections[name]

# Expose database instance
db_mongo = mongo_db if mongo_db is not None else InMemoryMongoMock()
